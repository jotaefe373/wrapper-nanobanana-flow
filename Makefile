.PHONY: setup login cuentas importar snapshot health snapshot-diff rec r rh rc rch t2i t2ih t2is t2ish t2v t2vh ls key creds clean help

VENV := .venv
PY := $(VENV)/bin/python

# Prompt: acepta PROMPT="texto" o PROMPT_FILE=archivo.txt
PROMPT_ARG = $(if $(PROMPT_FILE),--prompt-file $(PROMPT_FILE),--prompt "$(PROMPT)")

# Cuenta: ACCOUNT=x fuerza una; sin ACCOUNT las generaciones rotan entre todas
ACCOUNT_ARG = $(if $(ACCOUNT),--account $(ACCOUNT),)

help: ## Mostrar esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-8s\033[0m %s\n", $$1, $$2}'

setup: ## Instalar todo (venv + deps + Playwright)
	@./scripts/setup.sh

login: $(VENV) ## Login manual (crea o renueva cuenta) — make login ACCOUNT=x
	$(PY) cli.py --login $(ACCOUNT_ARG)

cuentas: $(VENV) ## Listar cuentas y la proxima en rotar
	$(PY) cli.py --accounts

importar: $(VENV) ## Clonar sesion de Chrome — make importar CHROME=correo ACCOUNT=x (sin CHROME lista cuentas)
	$(PY) cli.py --import-chrome $(if $(CHROME),"$(CHROME)",) $(ACCOUNT_ARG)

snapshot: $(VENV) ## Snapshot trazable del sitio -> history/ (API=1 agrega RPCs, 1 credito)
	$(PY) cli.py --snapshot $(if $(API),--api,) $(ACCOUNT_ARG)

health: $(VENV) ## Chequear selectores criticos (sin creditos)
	$(PY) cli.py --health $(ACCOUNT_ARG)

snapshot-diff: $(VENV) ## Diff entre los dos ultimos snapshots
	$(PY) cli.py --snapshot-diff

rec: $(VENV) ## Grabar macro — make rec [NAME=x]
	$(PY) cli.py --record $(if $(NAME),--name $(NAME),) $(ACCOUNT_ARG)

r: $(VENV) ## Replay visible — make r IMAGE=x PROMPT_FILE=x [MACRO=x]
	$(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG) --visible $(ACCOUNT_ARG)

rh: $(VENV) ## Replay headless — make rh IMAGE=x PROMPT_FILE=x [MACRO=x]
	$(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG) $(ACCOUNT_ARG)

rc: $(VENV) ## Replay visible con .enc (sin perfil)
	FLOW_USE_CREDENTIALS=true $(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG) --visible $(ACCOUNT_ARG)

rch: $(VENV) ## Replay headless con .enc (sin perfil)
	FLOW_USE_CREDENTIALS=true $(PY) cli.py --replay $(if $(MACRO),$(MACRO),) --image $(IMAGE) $(PROMPT_ARG) $(ACCOUNT_ARG)

t2i: $(VENV) ## Text-to-image visible — make t2i PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2 $(PROMPT_ARG) --visible $(ACCOUNT_ARG)

t2ih: $(VENV) ## Text-to-image headless — make t2ih PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2 $(PROMPT_ARG) $(ACCOUNT_ARG)

t2is: $(VENV) ## Text-to-image stealth visible — make t2is PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2-stealth $(PROMPT_ARG) --visible $(ACCOUNT_ARG)

t2ish: $(VENV) ## Text-to-image stealth headless — make t2ish PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-image2-stealth $(PROMPT_ARG) $(ACCOUNT_ARG)

t2v: $(VENV) ## Text-to-video visible — make t2v PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-video $(PROMPT_ARG) --visible $(ACCOUNT_ARG)

t2vh: $(VENV) ## Text-to-video headless — make t2vh PROMPT="x" o PROMPT_FILE=x.json
	$(PY) cli.py --replay text-to-video $(PROMPT_ARG) $(ACCOUNT_ARG)

ls: $(VENV) ## Listar macros grabados
	$(PY) cli.py --list

key: $(VENV) ## Generar clave de encriptacion
	$(PY) cli.py --gen-key

creds: $(VENV) ## Exportar credenciales encriptadas
	$(PY) cli.py --export-creds $(ACCOUNT_ARG)

clean: ## Limpiar venv, cache y outputs
	rm -rf $(VENV) __pycache__ core/__pycache__ flow/__pycache__ *.egg-info output/* session/*

$(VENV):
	@./scripts/setup.sh
