#!/bin/sh
set -eu

OLLAMA_PID=
STREAMLIT_PID=

cleanup() {
    if [ -n "$STREAMLIT_PID" ]; then
        kill "$STREAMLIT_PID" 2>/dev/null || true
    fi
    if [ -n "$OLLAMA_PID" ]; then
        kill "$OLLAMA_PID" 2>/dev/null || true
    fi
}

trap cleanup EXIT HUP INT TERM

ollama serve &
OLLAMA_PID=$!

attempt=0
until curl --fail --silent http://127.0.0.1:11434/api/tags >/dev/null; do
    if ! kill -0 "$OLLAMA_PID" 2>/dev/null; then
        echo "Ollama exited before its API became ready." >&2
        exit 1
    fi
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 60 ]; then
        echo "Ollama did not become ready within 120 seconds." >&2
        exit 1
    fi
    sleep 2
done

if ! ollama list | awk 'NR > 1 { print $1 }' | grep -F -x -q "$OLLAMA_MODEL"; then
    ollama pull "$OLLAMA_MODEL"
fi

streamlit run demo_app.py \
    --server.address 0.0.0.0 \
    --server.port "${PORT:-10000}" \
    --server.headless true &
STREAMLIT_PID=$!

wait "$STREAMLIT_PID"
