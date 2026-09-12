#!/usr/bin/env bash
# Rotina semanal: pede ao Claude Code para montar a próxima semana de treinos.
#
# Roda pelo LaunchAgent com.mtbnutrition.semana (domingo 19h). O modelo que monta
# a semana é o da assinatura do Claude Code, não uma API cobrada — foi a decisão
# de 12/09/2026, quando o crédito da Anthropic acabou e o dono optou por não
# pagar API. O passo a passo está em .claude/commands/semana.md.
set -euo pipefail

PROJETO="/Users/marcianocadore/projetoiaperformancenutri"
LOG="$HOME/Library/Logs/mtbnutrition-semana.log"

# O binário do Claude Code mora dentro da extensão do VS Code, cujo diretório
# carrega a versão no nome — resolver na hora evita a rotina quebrar calada no
# dia em que a extensão se atualizar.
CLAUDE="$(command -v claude || true)"
if [ -z "$CLAUDE" ]; then
  CLAUDE="$(ls -td "$HOME"/.vscode/extensions/anthropic.claude-code-*/resources/native-binary/claude 2>/dev/null | head -1 || true)"
fi
if [ -z "$CLAUDE" ] || [ ! -x "$CLAUDE" ]; then
  echo "[$(date)] claude não encontrado — rotina abortada" >> "$LOG"
  exit 1
fi

cd "$PROJETO"
echo "════════ [$(date)] gerando próxima semana ════════" >> "$LOG"
"$CLAUDE" -p "/semana" --output-format text >> "$LOG" 2>&1
echo "[$(date)] fim (saída $?)" >> "$LOG"
