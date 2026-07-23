import os

# Ollama host. Defaults to localhost (the Mac runs the model server locally);
# remote clients (e.g. Kali over LAN) export CTF_AI_HOST=192.168.1.11
HOST          = os.environ.get("CTF_AI_HOST", "localhost")
PORT          = 11434
LOCAL_MODEL   = "deepseek-r1:14b"      # local Ollama reasoning model
MODEL         = LOCAL_MODEL            # back-compat alias (older imports use config.MODEL)
FALLBACK      = "dolphin-llama3:8b"    # uncensored local model — refusal fallback (stays local)
NUM_CTX       = 8192
TEMPERATURE   = 0.1
MAX_STEPS     = 15
MAX_OBS_CHARS = 4000   # observation fed back to model (truncated if longer)
TASK_DIR      = ".agent"

# ── Remote "brain" (OpenAI-compatible gateway) ────────────────────────────────
# A large hosted model does the reasoning; the local machine still runs the tools.
# Only the API KEY is a secret — it comes from the env (sourced from
# ~/.config/ctf-toolchain/secrets.env, chmod 600, OUTSIDE this repo). Never commit it.
REMOTE_MODEL    = os.environ.get("CTF_REMOTE_MODEL", "qwen3.6-35b-a3b")
REMOTE_BASE_URL = os.environ.get("CTF_REMOTE_BASE_URL", "https://gateway.9arm.co/v1").rstrip("/")
REMOTE_API_KEY  = os.environ.get("CTF_REMOTE_API_KEY", "")
REMOTE_TIMEOUT  = int(os.environ.get("CTF_REMOTE_TIMEOUT", "300"))
# Output cap for the remote brain. Bounds runaway generation, latency and cost.
# NOTE: this gateway streams `reasoning_content` — the model's thinking counts
# against this budget too, so keep enough headroom that reasoning + the (small)
# final answer both fit, or the answer gets truncated. Env-overridable.
REMOTE_MAX_TOKENS = int(os.environ.get("CTF_REMOTE_MAX_TOKENS", "4096"))
# Assumed context window of the remote model — much larger than local NUM_CTX,
# used only to size history truncation (see context_char_budget).
REMOTE_NUM_CTX  = int(os.environ.get("CTF_REMOTE_NUM_CTX", "32768"))
# The gateway is behind Cloudflare, which 403s (error 1010) the default
# Python-urllib User-Agent. Send a browser-like UA so requests get through.
REMOTE_USER_AGENT = os.environ.get(
    "CTF_REMOTE_USER_AGENT",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
)

_CHARS_PER_TOKEN = 4   # rough estimate for budgeting message-history length


def context_char_budget(model: str | None) -> int:
    """Approx chars of message history to keep for `model`, leaving ~30% of its
    context window as headroom for the reply + system framing. Used by
    context.maybe_truncate so history is bounded by the ACTIVE model's window
    (local 8k vs remote 32k+) instead of a fixed message count."""
    ctx = REMOTE_NUM_CTX if is_remote(model) else NUM_CTX
    return int(ctx * 0.7 * _CHARS_PER_TOKEN)
# Remote is the DEFAULT brain; CTF_BRAIN=local (or --local) forces the Ollama path.
REMOTE_ENABLED  = os.environ.get("CTF_BRAIN", "remote").lower() != "local"

# The brain the agent uses unless a call overrides `model=`.
BRAIN_MODEL = REMOTE_MODEL if REMOTE_ENABLED else LOCAL_MODEL


def is_remote(model: str | None) -> bool:
    """True when `model` should be served by the remote OpenAI-compatible gateway."""
    return bool(model) and model == REMOTE_MODEL
