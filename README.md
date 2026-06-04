# Thoughtbench

Thoughtbench is a local desktop chat workbench for thinking-capable **Gemma 4**
and **Qwen3** models. It runs models from Hugging Face on your own Windows
machine, keeps your chats and Behaviour Profiles in local folders, and includes
profile-local knowledge retrieval for project notes, policies, and other
reference files.

This guide assumes you are using a **Windows 11** computer with an **NVIDIA GPU**.
The smoothest experience is on **12 GB+ VRAM**. An **8 GB VRAM** card can use the
project's automatic low-VRAM mode.

## Features

- Desktop Tk app with streaming chat, separate Thinking output, and markdown
  rendering.
- Curated Gemma 4 and Qwen3 model picker with optional Thinking Mode.
- Behaviour Profiles with separate system prompts, prompt history,
  conversations, transcripts, diagnostics, and knowledge files.
- Local `.md` / `.txt` knowledge indexing with BM25 retrieval and visible source
  notes.
- Token usage indicator that counts Assistant Behaviour, restored conversation,
  retrieved knowledge, and reserved reply budget.
- Windows setup assistant for Python 3.12, PyTorch CUDA packages, Pascal GPU
  compatibility, Hugging Face checks, optional pre-download, and app launch.
- PyInstaller build and user-local installer scripts for the desktop app.

## Requirements

- Windows 11.
- NVIDIA GPU with a current driver.
- 8 GB VRAM minimum for the smaller curated models; 12 GB+ VRAM is smoother.
- Python 3.12. The setup script expects Python Manager's `py` launcher, but an
  existing compatible `.venv` can also be reused.
- Enough disk space for the Python environment and Hugging Face model cache.
  The default E2B model can need roughly **10-20 GB** in cache; larger models
  need more.

## Quick Windows setup

These are local models, so setup depends on the computer's GPU, driver, Python
environment, and the ability to download from Hugging Face.

Before running the app for the first time:

1. Download or clone this project.
2. Open PowerShell in the project folder.
3. Check whether the computer looks suitable:

If Windows blocks local PowerShell scripts because of the execution policy, use
a temporary bypass for the current PowerShell window:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

This only affects the current PowerShell process. Alternatively, run a script
with a one-shot bypass:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\Setup-Thoughtbench.ps1 -CheckOnly
```

```powershell
.\scripts\Setup-Thoughtbench.ps1 -CheckOnly
```

The setup assistant checks the GPU, NVIDIA driver, disk space, Python
environment, PyTorch CUDA support, and whether Hugging Face authentication is
available. Login is optional for public model downloads.

If the assistant prints `ACTION NEEDED`, follow the final `Next step` it shows,
then run the check again.

When the check looks suitable, run the setup:

```powershell
.\scripts\Setup-Thoughtbench.ps1
```

This creates `.venv` and installs the Python dependencies when needed.

You can pre-download the default E2B model:

```powershell
.\scripts\Setup-Thoughtbench.ps1 -PreDownloadModel
```

Or pre-download one of the other curated models:

```powershell
.\scripts\Setup-Thoughtbench.ps1 -PreDownloadModel -ModelId google/gemma-4-E4B-it
.\scripts\Setup-Thoughtbench.ps1 -PreDownloadModel -ModelId Qwen/Qwen3-0.6B
```

To launch Thoughtbench after a successful setup:

```powershell
.\scripts\Setup-Thoughtbench.ps1 -Launch
```

The old `scripts\Setup-Gemma4.ps1` path remains as a compatibility wrapper, but
new documentation and examples use `Setup-Thoughtbench.ps1`.

The assistant cannot install NVIDIA drivers or install Python globally. This
project expects Python 3.12 to be managed with Python Manager:
https://github.com/python/pymanager. The setup assistant will tell you when a
manual Python or driver step is required.

## Project layout

```text
app.py                         desktop app entrypoint
chat.py                        interactive terminal chat
generate.py                    single-shot terminal generation
thoughtbench\                  app package
thoughtbench\config.py         app constants and curated model catalog
thoughtbench\knowledge.py      profile-local BM25 knowledge index
thoughtbench\persistence.py    profiles, prompt history, logs, saved state
thoughtbench\runtime.py        model runtime and streaming orchestration
thoughtbench\ui.py             Tk desktop UI
scripts\Setup-Thoughtbench.ps1 Windows setup/check/download/launch helper
scripts\Build.ps1              PyInstaller build helper
scripts\Install-ToPrograms.ps1 user-local installer
tests\                         unit tests for knowledge retrieval and injection
```

## Hugging Face model location

The model files are large and are downloaded by Hugging Face into its
local cache. The app asks which curated model to load at startup and
remembers the last choice globally in `%APPDATA%\Thoughtbench\settings.json`.
Expect the download/cache to need roughly **10-20 GB** for the E2B model and
substantially more for larger models, plus extra free space for Python packages
and temporary download files. Smaller Qwen3 models can be much lighter. By
default, the Hugging Face cache is usually under your Windows user profile.

To keep Hugging Face models off the system drive, set the Hugging Face cache
variables before downloading the model. This workspace keeps all model storage
under `D:\LLMProjects\HuggingFace\Hub`:

```powershell
[Environment]::SetEnvironmentVariable("HF_HOME", "D:\LLMProjects\HuggingFace", "User")
[Environment]::SetEnvironmentVariable("HF_HUB_CACHE", "D:\LLMProjects\HuggingFace\Hub", "User")
```

If you previously used `HUGGINGFACE_HUB_CACHE`, set `HF_HUB_CACHE` to the same
folder. `HUGGINGFACE_HUB_CACHE` is the older name and no longer takes precedence
over `HF_HUB_CACHE`.

Hugging Face-managed downloads live in folders like:

```text
D:\LLMProjects\HuggingFace\Hub\models--google--gemma-4-E2B-it
```

Manual local model folders, such as ONNX Runtime GenAI exports used by the C#
app, live under:

```text
D:\LLMProjects\HuggingFace\Hub\local\
```

Close and reopen PowerShell after setting it, then run:

```powershell
.\scripts\Setup-Thoughtbench.ps1 -PreDownloadModel
```

Use a folder on a drive with plenty of free space. The app will use the same
Hugging Face cache location when it starts.

## Manual developer setup

```powershell
# Create a venv with Python 3.12 using Python Manager's py launcher
py -3.12 -m venv .venv
.venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Optional: log in to Hugging Face if a download asks for authentication
hf auth login
```

Run from source:

```powershell
python app.py
```

## C# / ONNX CUDA implementation

The `csharp-implementation` branch contains a parallel C# port of Thoughtbench.
The Python app remains in place for comparison while the C# app reaches parity.

The C# solution is:

```text
Thoughtbench.CSharp.sln
src\Thoughtbench.App\       WPF desktop app
src\Thoughtbench.Core\      profiles, knowledge retrieval, diagnostics, prompt logic
src\Thoughtbench.Onnx\      ONNX Runtime GenAI CUDA backend
src\Thoughtbench.Cli\       thoughtbench chat/generate CLI
tests\Thoughtbench.Tests\   package-free C# test runner
```

This workspace targets `.NET 10`. Install the .NET 10 SDK and make sure it is
available on `PATH` before building or launching the C# app.

Run the C# setup check:

```powershell
.\scripts\Setup-Thoughtbench-CSharp.ps1 -CheckOnly
```

To download the Phi-3 Mini ONNX GenAI model from Hugging Face into the local
model area:

```powershell
hf download microsoft/Phi-3-mini-4k-instruct-onnx `
  --include "cuda/cuda-int4-rtn-block-32/*" `
  --local-dir D:\LLMProjects\HuggingFace\Hub\local\Thoughtbench\phi-3-mini-4k-instruct-onnx
```

The WPF app loads models with its in-app folder picker. Use **Browse** and select
the inner ONNX GenAI folder that contains `genai_config.json`, for example:

```text
D:\LLMProjects\HuggingFace\Hub\local\Thoughtbench\phi-3-mini-4k-instruct-onnx\cuda\cuda-int4-rtn-block-32
```

Launch the WPF app:

```powershell
.\scripts\Setup-Thoughtbench-CSharp.ps1 -Launch
```

Or run the CLI by passing a model folder explicitly:

```powershell
dotnet run --project .\src\Thoughtbench.Cli\Thoughtbench.Cli.csproj -- generate "Write a haiku" --model-path D:\LLMProjects\HuggingFace\Hub\local\Thoughtbench\phi-3-mini-4k-instruct-onnx\cuda\cuda-int4-rtn-block-32
dotnet run --project .\src\Thoughtbench.Cli\Thoughtbench.Cli.csproj -- chat --model-path D:\LLMProjects\HuggingFace\Hub\local\Thoughtbench\phi-3-mini-4k-instruct-onnx\cuda\cuda-int4-rtn-block-32
```

The first C# version expects a user-provided ONNX Runtime GenAI model folder.
The former Gemma/Qwen Hugging Face catalog is intentionally deferred until
converted ONNX artifacts are chosen and validated.

Build and test:

```powershell
dotnet build .\Thoughtbench.CSharp.sln
dotnet run --project .\tests\Thoughtbench.Tests\Thoughtbench.Tests.csproj
.\scripts\Build-CSharp.ps1
```

On first launch, the app asks where to create `.thoughtbench`. That folder is the
first Behaviour Profile. A Behaviour Profile stores its own saved Assistant
Behaviour (`system_prompt.md`), prompt history, current conversation, chat logs,
diagnostics logs, and optional knowledge files. The model weights are not stored
in this repo; Hugging Face downloads and caches them on the machine.

Use the left sidebar to find the main app areas. `Behaviour` contains the
Assistant Behaviour editor and prompt history. `Profiles` contains the active
profile selector plus actions to create a new profile or add an existing profile
folder. Switching profiles saves the current profile and restores the selected
profile's prompt and conversation.

Assistant Behaviour history is saved beside the current profile's prompt:

```text
.thoughtbench\system_prompt_history.json
```

Use the prompt history selector in the desktop app to restore an earlier
Assistant Behaviour. The Assistant Behaviour editor supports normal undo and
redo shortcuts while you are editing it.

The desktop app also saves the current profile's conversation in:

```text
.thoughtbench\conversation.json
```

Knowledge files for the current profile live in:

```text
.thoughtbench\knowledge\
```

The generated retrieval index lives beside them:

```text
.thoughtbench\knowledge_index\
```

When you reopen the app, the active profile's previous conversation is restored.
Use `Clear Conversation` to start fresh in the current profile. This resets that
profile's `conversation.json` to an empty conversation but does not delete
transcript, diagnostics log, knowledge, or knowledge index files.

Settings that remember the active and recent profiles are stored outside the
profile folders:

```text
%APPDATA%\Thoughtbench\settings.json
```

Older installs that already used `%APPDATA%\TestGemma4\settings.json` or a
single `.test.gemma4` profile folder are migrated by treating that existing
state as the first active Behaviour Profile. No files need to be moved manually.

If Git reports dubious ownership after cloning or moving the folder, trust the
clone path for the current Windows user:

```powershell
git config --global --add safe.directory <full-path-to-clone>
```

Example:

```powershell
git config --global --add safe.directory C:/Users/You/source/Thoughtbench
```

Build and install the desktop app:

```powershell
.\scripts\Build.ps1 -Clean
.\scripts\Install-ToPrograms.ps1 -Replace
```

Default install path:

```text
%LOCALAPPDATA%\Programs\Thoughtbench
```

Run the installed app:

```powershell
& "$env:LOCALAPPDATA\Programs\Thoughtbench\Thoughtbench.exe"
```

Custom install location:

```powershell
.\scripts\Install-ToPrograms.ps1 -InstallRoot "D:\Programs" -Replace
```

## Usage

### Interactive chat

```powershell
python chat.py            # normal mode
python chat.py --think    # enable thinking / reasoning mode
python chat.py --model-id google/gemma-4-E4B-it
python chat.py --model-id Qwen/Qwen3-0.6B --think
```

Commands inside the chat session:
- `/think` — toggle thinking mode on/off
- `/reset` — clear conversation history
- `/behaviour <instruction>` — rewrite Assistant Behaviour from advice

In the desktop app, type a behaviour change in the input box and click
`Rewrite Behaviour` to ask the loaded model to rewrite the saved Assistant Behaviour
instructions without sending the advice as a normal chat message.
The rewrite uses thinking mode internally; any thinking output appears in the
Thinking pane.

Thoughtbench asks which model to load before download/loading begins. The
curated choices are:

| Family | Model ID | Notes |
| --- | --- | --- |
| Gemma | `google/gemma-4-E2B-it` | Default local test model. |
| Gemma | `google/gemma-4-E4B-it` | Larger edge model. |
| Gemma | `google/gemma-4-26B-A4B-it` | Larger MoE model. |
| Gemma | `google/gemma-4-31B-it` | Largest curated Gemma option. |
| Qwen | `Qwen/Qwen3-0.6B` | Smallest Qwen3 model in this catalog. |
| Qwen | `Qwen/Qwen3-1.7B` | Small practical Qwen3 option. |
| Qwen | `Qwen/Qwen3-4B` | Balanced Qwen3 option. |
| Qwen | `Qwen/Qwen3-8B` | Strongest practical Qwen3 option in this catalog. |

All listed models use the same Thinking Mode switch. Gemma models emit channel
markers, while Qwen3 models use `<think>...</think>` blocks and are loaded with
`AutoTokenizer`. Larger models may need much more VRAM, disk space, download
time, and load time.

The desktop app can keep multiple Behaviour Profiles. Each profile has its own
Assistant Behaviour, prompt history, restored conversation, transcripts, and
diagnostics. Use the sidebar `Profiles` section to switch profiles, create a new
profile from the current prompt, or add an existing profile folder.

The bottom stats bar also shows token usage after the model has loaded. The
token count includes the current Assistant Behaviour, restored conversation, and
the configured `Max tokens` reply budget. The indicator changes colour as usage
approaches the model context window; sending is disabled only when the prompt
itself no longer fits.

The token readout looks like this:

```text
Tokens: 6,900/8,192 (84%) - input 5,876 + reply budget 1,024
```

The `input` number is everything sent before the model starts replying. The
reply budget is the reserved output room from `Max tokens`. The token part of
the stats bar is normal below 80%, yellow/orange at 80% or higher, and red at
95% or higher. It also turns red if the input alone exceeds the model context
window. If the overall total is yellow or red but sending is still enabled,
reduce `Max tokens`, shorten Assistant Behaviour, or clear older conversation
context.

The generation sliders can also affect response time. `Reply length` has the
most direct effect because it sets the maximum number of new tokens, but
`Creativity`, `Variety`, and `Choice pool` change sampling behaviour and can
make responses faster or slower depending on the prompt, GPU, and generated
text.

### Configuring Assistant Behaviour and knowledge

The Assistant Behaviour field is the app's system prompt. It is a good place for
stable instructions: tone, role, response style, formatting preferences,
decision rules, and small reference notes that should apply to every reply.
Everything in Assistant Behaviour is sent to the model on every message.

You can use it in a similar way to GPT Builder instructions by keeping two
sections in the prompt:

```text
## Instructions
- How the assistant should behave
- What it should prioritize
- How it should format answers

## Knowledge
- Compact facts, definitions, policies, examples, or project notes
- Only include material that is useful often enough to send every turn
```

For larger reference material, use profile knowledge files instead of pasting the
content into Assistant Behaviour. Each Behaviour Profile has a managed
`knowledge\` folder that supports `.md` and `.txt` files. Use the sidebar
`Knowledge` section to open the folder, add or edit files there, then rebuild
the index.

Thoughtbench uses a local BM25 keyword index for the first version of retrieval.
For each desktop chat message, it searches the active profile's knowledge index,
injects the most relevant snippets as temporary context, and shows a compact
`Knowledge: file.md#0001` source note when snippets are used. The desktop app
also has a collapsible `Retrieved Knowledge` panel with source IDs, BM25 scores,
matched terms, and snippet previews. Retrieved snippets are not saved into
`conversation.json`; only the normal user and assistant messages are persisted.

This first version is best for exact project knowledge such as command names,
file paths, settings, UI labels, policy terms, and error strings. Keep semantic
or always-needed behaviour rules in Assistant Behaviour. BM25 remains the
exact-match anchor; vector or hybrid retrieval is future work.

Retrieval uses per-profile settings saved in:

```text
.thoughtbench\knowledge_settings.json
```

Use `Knowledge` > `Knowledge Settings...` to tune:

- `top_k`
- `context_char_budget`
- `chunk_size`
- `chunk_overlap`
- `minimum_score`
- `minimum_matched_terms`

Changing chunk settings or editing knowledge files makes the index stale. If the
app detects this before retrieval, it shows `Knowledge index is stale - rebuild
recommended.` and skips old snippet injection until you rebuild the index.

Use the bottom stats bar to tune the prompt. The `input` token count includes
Assistant Behaviour, retrieved knowledge snippets, restored conversation, the
current user message, and chat template overhead. The reply budget comes from
`Max tokens`. A practical target is to keep total usage below about 80% of the
model context window for normal chat, and treat 95% as the danger zone.

As a starting point:

- Keep core instructions around 500-2,000 tokens.
- Keep always-on knowledge in Assistant Behaviour only when it is needed across
  many turns.
- Put larger project notes, policies, examples, and references in `.md` or
  `.txt` files under `knowledge\`, then rebuild the index after edits.
- Lower `Max tokens` when you want more room for prompt or conversation.
- Use `Clear Conversation` when an old restored conversation is taking context
  away from a new task.

Behaviour Profiles are useful for different agent setups. For example, create
one profile for coding, another for writing, and another for a project-specific
assistant with its own knowledge folder. Each profile keeps its own Assistant
Behaviour, history, conversation, transcripts, diagnostics, knowledge files, and
knowledge index.

To experiment safely, edit Assistant Behaviour, watch the token stats update,
then send a short test prompt. If a change makes the assistant worse, use the
prompt history selector to restore an earlier version.

To try knowledge retrieval quickly:

1. Open the desktop app and choose a model.
2. Open the sidebar `Knowledge` section and choose `Open Knowledge Folder`.
3. Add a small `.md` file such as `project-notes.md`.
4. Use `Rebuild Knowledge Index`.
5. Ask a question that uses words from the file.

If retrieval finds a match, the chat/status area shows the injected source chunk
before the assistant response. Expand `Retrieved Knowledge` to inspect the score,
matched terms, source, and snippet preview.

## Tests

The current test suite covers the profile-local knowledge index and retrieval
message injection. Run it from an activated virtual environment:

```powershell
python -m unittest discover tests
```

### Single-shot generation

```powershell
python generate.py "Explain quicksort in Python"
python generate.py --think "What is 25 * 37?"
python generate.py --model-id google/gemma-4-E4B-it "Explain quicksort in Python"
python generate.py --model-id Qwen/Qwen3-0.6B --think "What is 25 * 37?"
python generate.py --max-tokens 512 --system "You are a poet." "Write a haiku about GPU computing"
```

## VRAM usage

The default E2B-it model normally loads in BF16/FP16 and can use about 10 GB
VRAM, leaving roughly 2 GB headroom on a 12 GB card. Larger curated models need
more VRAM and disk cache, and may not fit consumer GPUs without quantization. On
GPUs below 12 GB VRAM, the app automatically tries 4-bit low-VRAM loading
instead.

Low-VRAM mode is slower than the normal 12 GB path, but it gives 8 GB cards a
usable route. Keep `Reply length` closer to 512-1024 tokens on 8 GB cards,
especially with Thinking Mode enabled.

GTX 10-series cards such as the GTX 1070 use Pascal compute capability 6.1.
Recent PyTorch CUDA 12.8 wheels do not support that GPU generation, so the setup
assistant switches those cards to the pinned CUDA 11.8 package set in
`requirements-pascal.txt`. If setup reports that the installed PyTorch wheel does
not support the GPU, run:

```powershell
.\scripts\Setup-Thoughtbench.ps1
```

That reinstalls the compatible package set inside `.venv`.

You can override model loading with the `THOUGHTBENCH_LOAD_MODE` environment variable:

```powershell
$env:THOUGHTBENCH_LOAD_MODE = "auto"   # default: 4-bit below 12 GB, normal otherwise
$env:THOUGHTBENCH_LOAD_MODE = "4bit"   # force low-VRAM quantized loading
$env:THOUGHTBENCH_LOAD_MODE = "bf16"   # force normal BF16/FP16 loading
```

The command-line helpers also accept `--load-mode`:

```powershell
python chat.py --load-mode 4bit
python generate.py --load-mode 4bit "Explain quicksort"
```

Monitor with `nvidia-smi`.

## Build the desktop executable

Put your icon PNG at:

```text
assets\app-icon.png
```

Then build from PowerShell:

```powershell
.\scripts\Build.ps1
```

The script installs the build dependencies from `requirements-build.txt`, converts
`assets\app-icon.png` to `assets\app-icon.ico`, and runs PyInstaller with
`Thoughtbench.spec`.

The executable is written to:

```text
dist\Thoughtbench\Thoughtbench.exe
```

Useful build options:

```powershell
.\scripts\Build.ps1 -Clean        # remove build/dist first
.\scripts\Build.ps1 -SkipInstall  # reuse already installed build deps
```

When replacing the app icon, use a clean rebuild so both the embedded executable
icon and the runtime Tk window icon are refreshed:

```powershell
.\scripts\Build.ps1 -Clean
.\scripts\Install-ToPrograms.ps1 -Replace
```

Windows Explorer and taskbar shortcuts may keep showing the previous icon from
the shell icon cache. If the rebuilt `dist\Thoughtbench\Thoughtbench.exe` has the
new icon but an installed shortcut still looks old, unpin and repin the app, or
restart Explorer/sign out and back in.

Install the built app under the current user's local programs folder:

```powershell
.\scripts\Install-ToPrograms.ps1
```

By default this installs to:

```text
%LOCALAPPDATA%\Programs\Thoughtbench
```

Earlier versions of this script hardcoded `E:\Programs` as the default install
root. The script is now computer-agnostic, so `E:\Programs` is only used when you
ask for it explicitly.

Choose a custom install location when needed:

```powershell
.\scripts\Install-ToPrograms.ps1 -InstallRoot "E:\Programs"
```

That installs to:

```text
E:\Programs\Thoughtbench
```

Or install to an exact target folder:

```powershell
.\scripts\Install-ToPrograms.ps1 -InstallPath "D:\Tools\Thoughtbench"
```

Replace an existing installed copy:

```powershell
.\scripts\Install-ToPrograms.ps1 -Replace
```

Replace an existing copy in a custom location:

```powershell
.\scripts\Install-ToPrograms.ps1 -InstallRoot "E:\Programs" -Replace
```

The executable does not bundle model weights. On first launch it uses
the same Hugging Face cache/download flow as the Python app.

### Why the build is large

The PyInstaller build is expected to be large. Even without bundling model
weights, the app has to include a Python runtime plus ML dependencies such as
PyTorch, Transformers, Accelerate, Tokenizers, SentencePiece, and CUDA/PyTorch
support libraries.

Most of the size is in:

```text
dist\Thoughtbench\_internal\
```

This project intentionally uses PyInstaller's one-folder layout:

```text
dist\Thoughtbench\Thoughtbench.exe
dist\Thoughtbench\_internal\
```

Avoid `--onefile` for this app unless there is a specific reason. It would still
be large, and startup is usually slower because the bundled files have to be
unpacked before launch.

For daily use on your own machine, running from the virtual environment can be
lighter and easier to update:

```powershell
.\.venv\Scripts\python.exe app.py
```

Use the PyInstaller build when you want a self-contained app folder that can be
installed under your local programs folder or another explicit `-InstallRoot`.

## Diagnostics

Use the sidebar `Diagnostics` section to inspect explicit app diagnostics and
captured stderr errors. Routine stdout, such as model loading or download
progress printed by libraries, continues to go to the terminal and is not
mirrored into the in-app Diagnostics section. Diagnostics are captured even
while the section is not selected and are saved beside the current profile's
chat logs:

```text
.thoughtbench\diagnostics_YYYYMMDD_HHMMSS.log
```
