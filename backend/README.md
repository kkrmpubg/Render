# GameDrop bypass backend

This backend exposes a small API that can be used by GameDrop to resolve bypass availability without exposing the GitHub token in the client app.

## Deploy to Render

1. Create a new Web Service in Render.
2. Connect this folder as the root directory.
3. Render will use the included render.yaml.
4. Set the environment variables:
   - GITHUB_TOKEN
   - GH_TOKEN (optional)
   - REMOTE_BYPASS_URL (optional)
5. Deploy.

## Endpoints

- GET /health
- GET /remote-bypass-appids
- GET /bypass-info?appid=1245620
