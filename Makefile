.PHONY: setup login rec r rh rc rch t2i t2ih t2is t2ish ls key creds clean help

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

t2i: $(VENV) ## Text-to-image visible — make t2i PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2 $(PROMPT_ARG) --visible

t2ih: $(VENV) ## Text-to-image headless — make t2ih PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2 $(PROMPT_ARG)

t2is: $(VENV) ## Text-to-image stealth visible — make t2is PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2-stealth $(PROMPT_ARG) --visible

t2ish: $(VENV) ## Text-to-image stealth headless — make t2ish PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2-stealth $(PROMPT_ARG)

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
