# A2S VS Code client

This minimal extension calls the existing `a2s serve` API.

1. Run `npm install` in this directory.
2. Run `npm run compile`.
3. Open this directory in VS Code and press `F5`.

Configure `a2s.url` and `a2s.workspace` in VS Code settings. Use
`A2S: Configure API Token` to store the bearer token in VS Code SecretStorage;
the token is never kept in `package.json` or source code. Start the API with
`python -m a2s serve` from the project workspace.