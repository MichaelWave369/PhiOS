# Model and Dataset Licensing

PhiOS code can be MIT-licensed without implying that AI model weights, datasets, or hosted model services are MIT-licensed.

## Current repository rule

As of the Phi Commons migration, this repository does not grant a license to third-party model weights.

PhiOS adapters, routing code, local configuration, prompts, schemas, and integration code that are original to PhiOS are covered by the repository license unless otherwise noted.

A model downloaded or connected separately remains governed by that model provider's terms.

Examples include local or remote models used through:

- Ollama;
- MCP-connected model services;
- local inference runtimes;
- future PhiVessel model adapters.

## Release requirement

If a future release bundles model weights, datasets, embeddings, fonts, media assets, or other separately licensed material, the release must document:

1. the exact component and version;
2. its upstream source;
3. its governing license or terms;
4. whether redistribution is permitted;
5. any required attribution or notice.

No model should be described as part of the MIT grant merely because PhiOS can run it.
