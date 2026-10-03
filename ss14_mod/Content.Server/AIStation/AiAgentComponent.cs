namespace Content.Server.AIStation;

/// <summary>
/// Attached to every autonomous AI character (and browser-possessed character) on the station.
/// Stores identity, job role, personality prompt, current goal, inner monologue, and memory state.
/// </summary>
[RegisterComponent]
public sealed partial class AiAgentComponent : Component
{
    [DataField]
    public string AgentId = string.Empty;

    [DataField]
    public string CharacterName = string.Empty;

    [DataField]
    public string JobId = "Passenger";

    [DataField]
    public string RoleTitle = "Passenger";

    [DataField]
    public string Department = "Civilian";

    [DataField]
    public string Personality = string.Empty;

    [DataField]
    public string SecretObjective = string.Empty;

    [DataField]
    public bool IsAntagonist;

    [DataField]
    public bool BrowserControlled;

    [DataField]
    public string CurrentTask = "Exploring station";

    [DataField]
    public string LastThought = string.Empty;

    [DataField]
    public string LastSpeech = string.Empty;

    [DataField]
    public string TargetRoom = string.Empty;
}
