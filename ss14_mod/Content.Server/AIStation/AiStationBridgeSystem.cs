using System.Collections.Concurrent;
using System.IO;
using System.Linq;
using System.Net;
using System.Numerics;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Content.Server.Chat.Systems;
using Content.Server.Doors.Systems;
using Content.Server.GameTicking;
using Content.Server.Hands.Systems;
using Content.Server.Mind;
using Content.Server.NPC.Systems;
using Content.Server.Roles;
using Content.Server.Station.Components;
using Content.Shared.Chat;
using Content.Shared.Damage.Components;
using Content.Shared.Damage.Systems;
using Content.Shared.Doors.Components;
using Content.Shared.Hands.Components;
using Content.Shared.Interaction;
using Content.Shared.Mobs;
using Content.Shared.Mobs.Components;
using Content.Shared.Mobs.Systems;
using Content.Shared.Pinpointer;
using Content.Shared.Preferences;
using Content.Shared.Roles;
using Content.Shared.Station.Components;
using Content.Shared.Station.Systems;
using Content.Shared.SurveillanceCamera.Components;
using Robust.Shared.Map;
using Robust.Shared.Prototypes;
using Robust.Shared.Timing;

namespace Content.Server.AIStation;

/// <summary>
/// Embedded HTTP/JSON bridge inside Space Station 14's Content.Server.
/// Exposes real-time station telemetry, surveillance camera feeds, and AI character control endpoints
/// on http://127.0.0.1:12120/ so the OpenAI Agent Orchestrator & Web Control Dashboard drive real SS14 entities.
/// </summary>
public sealed class AiStationBridgeSystem : EntitySystem
{
    [Dependency] private readonly IGameTiming _timing = default!;
    [Dependency] private readonly IPrototypeManager _protoMan = default!;
    [Dependency] private readonly ChatSystem _chat = default!;
    [Dependency] private readonly DoorSystem _door = default!;
    [Dependency] private readonly HandsSystem _hands = default!;
    [Dependency] private readonly SharedInteractionSystem _interaction = default!;
    [Dependency] private readonly MindSystem _mind = default!;
    [Dependency] private readonly MobStateSystem _mobState = default!;
    [Dependency] private readonly DamageableSystem _damageable = default!;
    [Dependency] private readonly NPCSteeringSystem _steering = default!;
    [Dependency] private readonly RoleSystem _roles = default!;
    [Dependency] private readonly ServerGameTicker _ticker = default!;
    [Dependency] private readonly SharedTransformSystem _xform = default!;
    [Dependency] private readonly StationSpawningSystem _stationSpawning = default!;

    private HttpListener? _listener;
    private CancellationTokenSource? _cts;
    private readonly ConcurrentQueue<BridgeCommand> _commandQueue = new();
    private readonly ConcurrentQueue<ChatRecord> _chatHistory = new();
    private string _cachedStateJson = "{}";
    private float _snapshotAccumulator;
    private const float SnapshotInterval = 0.25f;

    public override void Initialize()
    {
        base.Initialize();

        SubscribeLocalEvent<EntitySpokeEvent>(OnEntitySpoke);

        StartHttpBridge();
    }

    public override void Shutdown()
    {
        base.Shutdown();
        StopHttpBridge();
    }

    private void StartHttpBridge()
    {
        try
        {
            var portStr = Environment.GetEnvironmentVariable("SS14_AI_BRIDGE_PORT") ?? "12120";
            if (!int.TryParse(portStr, out var port))
                port = 12120;

            _cts = new CancellationTokenSource();
            _listener = new HttpListener();
            _listener.Prefixes.Add($"http://127.0.0.1:{port}/");
            _listener.Prefixes.Add($"http://localhost:{port}/");
            _listener.Start();

            Log.Info($"[AiStationBridge] Started embedded SS14 HTTP bridge on port {port}");
            _ = Task.Run(() => AcceptLoopAsync(_cts.Token));
        }
        catch (Exception ex)
        {
            Log.Error($"[AiStationBridge] Failed to start HTTP listener: {ex.Message}");
        }
    }

    private void StopHttpBridge()
    {
        try
        {
            _cts?.Cancel();
            _listener?.Stop();
            _listener?.Close();
        }
        catch
        {
            // Ignore shutdown exceptions
        }
    }

    private async Task AcceptLoopAsync(CancellationToken token)
    {
        while (!token.IsCancellationRequested && _listener is { IsListening: true })
        {
            try
            {
                var ctx = await _listener.GetContextAsync();
                _ = Task.Run(() => HandleHttpRequest(ctx), token);
            }
            catch (Exception)
            {
                if (token.IsCancellationRequested)
                    break;
            }
        }
    }

    private void HandleHttpRequest(HttpListenerContext ctx)
    {
        try
        {
            var req = ctx.Request;
            var res = ctx.Response;
            res.Headers.Add("Access-Control-Allow-Origin", "*");
            res.Headers.Add("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
            res.Headers.Add("Access-Control-Allow-Headers", "Content-Type");

            if (req.HttpMethod == "OPTIONS")
            {
                res.StatusCode = 204;
                res.Close();
                return;
            }

            var path = req.Url?.AbsolutePath ?? "/";

            if (req.HttpMethod == "GET" && (path == "/state" || path == "/"))
            {
                WriteJsonResponse(res, _cachedStateJson);
                return;
            }

            if (req.HttpMethod == "POST" && path == "/command")
            {
                using var reader = new StreamReader(req.InputStream, req.ContentEncoding);
                var body = reader.ReadToEnd();
                var cmd = JsonSerializer.Deserialize<BridgeCommand>(body, new JsonSerializerOptions
                {
                    PropertyNameCaseInsensitive = true
                });

                if (cmd != null)
                {
                    _commandQueue.Enqueue(cmd);
                    WriteJsonResponse(res, "{\"ok\":true}");
                }
                else
                {
                    res.StatusCode = 400;
                    WriteJsonResponse(res, "{\"ok\":false,\"error\":\"invalid_command\"}");
                }
                return;
            }

            res.StatusCode = 404;
            WriteJsonResponse(res, "{\"ok\":false,\"error\":\"not_found\"}");
        }
        catch (Exception ex)
        {
            try
            {
                ctx.Response.StatusCode = 500;
                WriteJsonResponse(ctx.Response, JsonSerializer.Serialize(new { ok = false, error = ex.Message }));
            }
            catch
            {
                // Ignore secondary failure
            }
        }
    }

    private static void WriteJsonResponse(HttpListenerResponse res, string json)
    {
        var bytes = Encoding.UTF8.GetBytes(json);
        res.ContentType = "application/json; charset=utf-8";
        res.ContentLength64 = bytes.Length;
        res.OutputStream.Write(bytes, 0, bytes.Length);
        res.Close();
    }

    private void OnEntitySpoke(EntityUid uid, Component comp, EntitySpokeEvent args)
    {
        var coords = _xform.GetMoverCoordinates(uid);
        _chatHistory.Enqueue(new ChatRecord
        {
            SpeakerUid = (int)uid,
            SpeakerName = Name(uid),
            Message = args.Message,
            Channel = args.Channel?.ID ?? "Local",
            X = coords.X,
            Y = coords.Y,
            Timestamp = _timing.CurTime.TotalSeconds
        });

        while (_chatHistory.Count > 150)
        {
            _chatHistory.TryDequeue(out _);
        }
    }

    public override void Update(float frameTime)
    {
        base.Update(frameTime);

        // Process queued commands from OpenAI Orchestrator / Web Browser
        while (_commandQueue.TryDequeue(out var cmd))
        {
            try
            {
                ExecuteCommand(cmd);
            }
            catch (Exception ex)
            {
                Log.Error($"[AiStationBridge] Error executing command '{cmd.Action}': {ex}");
            }
        }

        _snapshotAccumulator += frameTime;
        if (_snapshotAccumulator >= SnapshotInterval)
        {
            _snapshotAccumulator = 0f;
            RebuildStateSnapshot();
        }
    }

    private void ExecuteCommand(BridgeCommand cmd)
    {
        switch (cmd.Action.ToLowerInvariant())
        {
            case "spawn_agent":
                SpawnAiAgent(cmd);
                break;

            case "move_to":
                if (TryFindAgentEntity(cmd.AgentId, out var moveUid, out var moveComp))
                {
                    var xform = Transform(moveUid);
                    var targetCoords = new EntityCoordinates(xform.ParentUid.IsValid() ? xform.ParentUid : xform.GridUid ?? moveUid, cmd.X, cmd.Y);
                    _steering.Register(moveUid, targetCoords);
                    if (!string.IsNullOrEmpty(cmd.Task))
                        moveComp.CurrentTask = cmd.Task;
                    if (!string.IsNullOrEmpty(cmd.Thought))
                        moveComp.LastThought = cmd.Thought;
                }
                break;

            case "stop_move":
                if (TryFindAgentEntity(cmd.AgentId, out var stopUid, out _))
                {
                    _steering.Unregister(stopUid);
                }
                break;

            case "say":
                if (TryFindAgentEntity(cmd.AgentId, out var sayUid, out var sayComp) && !string.IsNullOrWhiteSpace(cmd.Text))
                {
                    sayComp.LastSpeech = cmd.Text;
                    if (!string.IsNullOrEmpty(cmd.Thought))
                        sayComp.LastThought = cmd.Thought;
                    _chat.TrySendInGameICMessage(sayUid, cmd.Text, InGameICChatType.Speak, false, ignoreActionBlocker: true);
                }
                break;

            case "whisper":
                if (TryFindAgentEntity(cmd.AgentId, out var whispUid, out _) && !string.IsNullOrWhiteSpace(cmd.Text))
                {
                    _chat.TrySendInGameICMessage(whispUid, cmd.Text, InGameICChatType.Whisper, false, ignoreActionBlocker: true);
                }
                break;

            case "emote":
                if (TryFindAgentEntity(cmd.AgentId, out var emoteUid, out _) && !string.IsNullOrWhiteSpace(cmd.Text))
                {
                    _chat.TrySendInGameICMessage(emoteUid, cmd.Text, InGameICChatType.Emote, false, ignoreActionBlocker: true);
                }
                break;

            case "toggle_door":
                var doorUid = new EntityUid(cmd.TargetUid);
                if (Exists(doorUid) && TryComp<DoorComponent>(doorUid, out var doorComp))
                {
                    EntityUid? actor = null;
                    if (TryFindAgentEntity(cmd.AgentId, out var agentUid, out _))
                        actor = agentUid;
                    _door.TryToggleDoor(doorUid, doorComp, actor);
                }
                break;

            case "interact":
                var targetEnt = new EntityUid(cmd.TargetUid);
                if (TryFindAgentEntity(cmd.AgentId, out var interUid, out _) && Exists(targetEnt))
                {
                    var tCoords = Transform(targetEnt).Coordinates;
                    _interaction.UserInteraction(interUid, tCoords, targetEnt);
                }
                break;

            case "pickup":
                var itemEnt = new EntityUid(cmd.TargetUid);
                if (TryFindAgentEntity(cmd.AgentId, out var pickUid, out _) && Exists(itemEnt))
                {
                    _hands.TryPickupAnyHand(pickUid, itemEnt, checkActionBlocker: false);
                }
                break;

            case "drop":
                if (TryFindAgentEntity(cmd.AgentId, out var dropUid, out _))
                {
                    _hands.TryDrop(dropUid, checkActionBlocker: false);
                }
                break;

            case "heal":
                if (TryFindAgentEntity(cmd.AgentId, out var healUid, out _))
                {
                    _damageable.ClearAllDamage(healUid);
                }
                break;

            case "announce":
                var station = FindPrimaryStation();
                if (station != EntityUid.Invalid && !string.IsNullOrWhiteSpace(cmd.Text))
                {
                    _chat.DispatchStationAnnouncement(station, cmd.Text, string.IsNullOrEmpty(cmd.Sender) ? "Central Command" : cmd.Sender);
                }
                break;
        }
    }

    private void SpawnAiAgent(BridgeCommand cmd)
    {
        var station = FindPrimaryStation();
        var jobId = string.IsNullOrWhiteSpace(cmd.JobId) ? "Passenger" : cmd.JobId;
        var charName = string.IsNullOrWhiteSpace(cmd.Name) ? $"AI-{ jobId }" : cmd.Name;

        var profile = HumanoidCharacterProfile.RandomWithSpecies().WithName(charName);
        ProtoId<JobPrototype> jobProtoId = new(jobId);

        EntityUid? mob = null;
        if (station != EntityUid.Invalid)
        {
            mob = _stationSpawning.SpawnPlayerCharacterOnStation(station, jobProtoId, profile);
        }

        if (mob == null || !mob.Value.IsValid())
        {
            // Fallback: spawn directly on station grid
            var gridUid = FindPrimaryStationGrid();
            if (gridUid == EntityUid.Invalid)
                return;
            var spawnCoords = new EntityCoordinates(gridUid, new Vector2(cmd.X, cmd.Y));
            mob = _stationSpawning.SpawnPlayerMob(spawnCoords, jobProtoId, profile, station != EntityUid.Invalid ? station : null);
        }

        var entity = mob.Value;
        var mind = _mind.CreateMind(null, charName);
        _mind.TransferTo(mind.Owner, entity);
        if (_protoMan.HasIndex(jobProtoId))
        {
            _roles.MindAddJobRole(mind.Owner, mind.Comp, silent: true, jobPrototype: jobId);
        }

        var aiComp = EnsureComp<AiAgentComponent>(entity);
        aiComp.AgentId = string.IsNullOrWhiteSpace(cmd.AgentId) ? $"agent-{(int)entity}" : cmd.AgentId;
        aiComp.CharacterName = charName;
        aiComp.JobId = jobId;
        aiComp.RoleTitle = jobId;
        aiComp.Department = string.IsNullOrWhiteSpace(cmd.Department) ? "Civilian" : cmd.Department;
        aiComp.Personality = cmd.Personality ?? string.Empty;
        aiComp.SecretObjective = cmd.SecretObjective ?? string.Empty;
        aiComp.IsAntagonist = cmd.IsAntagonist;
        aiComp.CurrentTask = "Starting shift on NSS Saltern";
    }

    private EntityUid FindPrimaryStation()
    {
        var query = EntityQueryEnumerator<StationDataComponent, StationSpawningComponent>();
        while (query.MoveNext(out var uid, out _, out _))
        {
            return uid;
        }
        return EntityUid.Invalid;
    }

    private EntityUid FindPrimaryStationGrid()
    {
        var query = EntityQueryEnumerator<StationDataComponent>();
        while (query.MoveNext(out _, out var data))
        {
            foreach (var grid in data.Grids)
            {
                if (Exists(grid))
                    return grid;
            }
        }
        return EntityUid.Invalid;
    }

    private bool TryFindAgentEntity(string agentId, out EntityUid uid, out AiAgentComponent comp)
    {
        var query = EntityQueryEnumerator<AiAgentComponent>();
        while (query.MoveNext(out var ent, out var ai))
        {
            if (ai.AgentId == agentId || ((int)ent).ToString() == agentId)
            {
                uid = ent;
                comp = ai;
                return true;
            }
        }
        uid = EntityUid.Invalid;
        comp = default!;
        return false;
    }

    private void RebuildStateSnapshot()
    {
        var agents = new List<object>();
        var agentQuery = EntityQueryEnumerator<AiAgentComponent, TransformComponent>();
        while (agentQuery.MoveNext(out var uid, out var ai, out var xform))
        {
            var pos = xform.Coordinates;
            var totalDmg = _damageable.GetTotalDamage(uid).Float();
            var mobStateStr = "Alive";
            if (_mobState.IsDead(uid))
                mobStateStr = "Dead";
            else if (_mobState.IsCritical(uid))
                mobStateStr = "Critical";

            var heldItems = new List<string>();
            if (TryComp<HandsComponent>(uid, out var handsComp))
            {
                foreach (var held in _hands.EnumerateHeld((uid, handsComp)))
                {
                    heldItems.Add(Name(held));
                }
            }

            agents.Add(new
            {
                uid = (int)uid,
                id = ai.AgentId,
                name = ai.CharacterName,
                job = ai.JobId,
                department = ai.Department,
                personality = ai.Personality,
                secretObjective = ai.SecretObjective,
                isAntagonist = ai.IsAntagonist,
                browserControlled = ai.BrowserControlled,
                currentTask = ai.CurrentTask,
                lastThought = ai.LastThought,
                lastSpeech = ai.LastSpeech,
                x = Math.Round(pos.X, 2),
                y = Math.Round(pos.Y, 2),
                rot = Math.Round(_xform.GetWorldRotation(xform).Theta, 2),
                health = Math.Max(0f, 100f - totalDmg),
                damage = totalDmg,
                status = mobStateStr,
                inventory = heldItems
            });
        }

        var cameras = new List<object>();
        var camQuery = EntityQueryEnumerator<SurveillanceCameraComponent, TransformComponent>();
        while (camQuery.MoveNext(out var uid, out var cam, out var xform))
        {
            cameras.Add(new
            {
                uid = (int)uid,
                id = string.IsNullOrEmpty(cam.CameraId) ? Name(uid) : cam.CameraId,
                active = cam.Active,
                x = Math.Round(xform.Coordinates.X, 2),
                y = Math.Round(xform.Coordinates.Y, 2)
            });
        }

        var doors = new List<object>();
        var doorQuery = EntityQueryEnumerator<DoorComponent, TransformComponent>();
        while (doorQuery.MoveNext(out var uid, out var door, out var xform))
        {
            doors.Add(new
            {
                uid = (int)uid,
                open = door.State == DoorState.Open || door.State == DoorState.Opening,
                x = Math.Round(xform.Coordinates.X, 2),
                y = Math.Round(xform.Coordinates.Y, 2)
            });
        }

        var payload = new
        {
            engine = "SpaceStation14.Content.Server (RobustToolbox C#)",
            roundId = _ticker.RoundId,
            curTime = Math.Round(_timing.CurTime.TotalSeconds, 1),
            agents,
            cameras,
            doors,
            chat = _chatHistory.ToArray()
        };

        _cachedStateJson = JsonSerializer.Serialize(payload);
    }

    private sealed class BridgeCommand
    {
        public string Action { get; set; } = string.Empty;
        public string AgentId { get; set; } = string.Empty;
        public string Name { get; set; } = string.Empty;
        public string JobId { get; set; } = "Passenger";
        public string Department { get; set; } = "Civilian";
        public string? Personality { get; set; }
        public string? SecretObjective { get; set; }
        public bool IsAntagonist { get; set; }
        public float X { get; set; }
        public float Y { get; set; }
        public int TargetUid { get; set; }
        public string? Text { get; set; }
        public string? Thought { get; set; }
        public string? Task { get; set; }
        public string? Sender { get; set; }
    }

    private sealed class ChatRecord
    {
        public int SpeakerUid { get; set; }
        public string SpeakerName { get; set; } = string.Empty;
        public string Message { get; set; } = string.Empty;
        public string Channel { get; set; } = "Local";
        public float X { get; set; }
        public float Y { get; set; }
        public double Timestamp { get; set; }
    }
}
