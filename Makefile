.PHONY: setup login rec r rh rc rch ls key creds clean help

VENV := .venv
PY := $(VENV)/bin/python

# Prompt: acepta PROMPT="texto" o PROMPT_FILE=archivo.txt
PROMPT_ARG = $(if $(PROMPT_FILE),--prompt-file $(PROMPT_FILE),--prompt "$(PROMPT)")

# Simular sin perfil (para rc/rch)
define NO_PROFILE
	@if [ -d session/chrome-profile ]; then mv session/chrome-profile session/_chrome-profile-bak; fi
endef
define RESTORE_PROFILE
	if [ -d session/_chrome-profile-bak ]; then mv session/_chrome-profile-bak session/chrome-profile; fi
endef

help: ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

setup: ## Instalar todo (venv + deps + Playwright)
	@./scripts/setup.sh

login: $(VENV) ## Login manual en Google
	$(PY) cli.py --login

rec: $(VENV) ## Grabar macro — make rec [NAME=x]
	$(PY) cli.py --record $(if $(NAME),--name $(NAME),)

r: $(VENV) ## Replay visible — make r IMAGE=x PROMPT_FILE=x [MACRO=x]
	$(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG) --visible

rh: $(VENV) ## Replay headless — make rh IMAGE=x PROMPT_FILE=x [MACRO=x]
	$(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG)

rc: $(VENV) ## Replay visible con .enc (sin perfil)
	$(NO_PROFILE)
	$(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG) --visible; \
	STATUS=$$?; $(RESTORE_PROFILE); exit $$STATUS

rch: $(VENV) ## Replay headless con .enc (sin perfil)
	$(NO_PROFILE)
	$(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG); \
	STATUS=$$?; $(RESTORE_PROFILE); exit $$STATUS

ls: $(VENV) ## Listar macros grabados
	$(PY) cli.py --list

key: $(VENV) ## Generar clave de encriptacion
	$(PY) cli.py --gen-key

creds: $(VENV) ## Exportar credenciales encriptadas
	$(PY) cli.py --export-creds

clean: ## Limpiar venv, cache y outputs
	rm -rf $(VENV) __pycache__ core/__pycache__ flow/__pycache__ *.egg-info output/* session/*

$(VENV):
	@./scripts/setup.sh
