// Start NeteaseCloudMusicApi and verify it responds.
const { serveNcmApi } = require("NeteaseCloudMusicApi");

serveNcmApi({
    port: 3000,
    forceHost: "localhost",
}).then((server) => {
    console.log("NeteaseCloudMusicApi listening on http://localhost:3000");
}).catch((e) => {
    console.error("Failed to start:", e);
    process.exit(1);
});