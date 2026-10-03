/**
 * Native Space Station 14 (Content.Client + Content.Server) Browser Redirector
 * Ensures any cached HTML page immediately loads the real C# OpenGL client via noVNC/websockify.
 */
(function () {
  if (!document.getElementById("screen")) {
    window.location.replace("/?native=" + Date.now());
  }
})();
