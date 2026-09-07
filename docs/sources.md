# Interface sources

Checked 2026-09-06. Proprietary interface details come from Siemens documentation; MCP/Codex/runtime behavior comes from the respective project maintainers. No community claims are used as evidence of compatibility.

- [Siemens: Installing TIA Portal Openness](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/basics/installation/installing-tia-portal-openness): option installation, matching versions and Siemens TIA Openness local group.
- [Siemens: Connecting to TIA Portal](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/tia-portal-openness-api/general-functions/connecting-to-the-tia-portal): creating a UI instance, assembly resolution and permission prompts.
- [Siemens: Access software target](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/tia-portal-openness-api/functions-for-projects-and-project-data/access-software-target): `IEngineeringServiceProvider.GetService<SoftwareContainer>()` and `PlcSoftware`.
- [Siemens: Generating blocks from source](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/tia-portal-openness-api/functions-for-accessing-the-data-of-a-plc-device/blocks/generating-blocks-from-source): external source generation, ASCII requirement and offline precondition.
- [Siemens: Importing block](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/export/import/importing/exporting-data-of-a-plc-device/blocks/importing-block): XML block import, supported program languages and explicit Override option.
- [Siemens: Compiling a project](https://docs.tia.siemens.cloud/r/en-us/v20/tia-portal-openness-api-for-automation-of-engineering-workflows/tia-portal-openness-api/functions-for-projects-and-project-data/compiling-a-project): `ICompilable.Compile()`, recursive compiler diagnostics and offline requirement.
- [Siemens: External source basics](https://docs.tia.siemens.cloud/r/en-us/v20/creating-and-managing-blocks/using-external-source-files-for-stl-and-scl/basics-of-using-external-source-files): generating source can overwrite existing named blocks/types.
- [OpenAI: Codex MCP](https://developers.openai.com/codex/mcp): local stdio servers and Codex TOML setup.
- [MCP: stdio transport specification](https://modelcontextprotocol.io/specification/2025-03-26/basic/transports): newline-delimited UTF-8 JSON-RPC on stdin/stdout.
- [Python.NET: embedding .NET](https://pythonnet.github.io/pythonnet/python.html): explicit `netfx` runtime loading, CLR assembly references, generic methods and delegates.
- [Python.NET 3.0.5 package](https://pypi.org/project/pythonnet/3.0.5/): the pinned Windows interop dependency.

Mapping these documented C# calls through Python.NET is this project's implementation choice. Documentation review and API doubles cannot establish real TIA compatibility; that requires the separate Windows acceptance run.
