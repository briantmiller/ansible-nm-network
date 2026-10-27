# Build and test the Ansible collection.  Run `make help` for targets.
SHELL := /bin/bash
NAMESPACE := $(shell awk '/^namespace:/{print $$2}' galaxy.yml)
NAME      := $(shell awk '/^name:/{print $$2}' galaxy.yml)
VERSION   := $(shell awk '/^version:/{print $$2}' galaxy.yml)
RPMLINT   ?= rpmlint
TARBALL   := dist/$(NAMESPACE)-$(NAME)-$(VERSION).tar.gz

.PHONY: help deps test sanity dryrun build install rpm rpm-container rpmlint clean version namespace

help:            ## List targets
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

deps:            ## Install Python dev tools and the community.general dependency
	python3 -m pip install -r requirements-dev.txt
	ansible-galaxy collection install -r requirements.yml -p .collections

test:            ## Run parser unit tests (no NetworkManager needed)
	python3 -m pytest -q tests/unit

sanity:          ## Run ansible-test sanity checks
	scripts/sanity.sh

dryrun:          ## Check-mode run of the example config against a stub nmcli
	scripts/dryrun.sh

build: test      ## Run tests, then build dist/<namespace>-<name>-<version>.tar.gz
	scripts/build.sh

install: build   ## Build and install the collection for the current user
	ansible-galaxy collection install --force $(TARBALL)

rpm:            ## Build the SRPM and noarch RPM on an EL host into dist/rpm/ (runs the tests in %check)
	scripts/build-rpm.sh $(RPMBUILD_ARGS)

rpm-container:   ## Build the RPMs in an EL10 container (podman or docker)
	scripts/build-rpm-container.sh $(RPMBUILD_ARGS)

rpmlint:         ## Lint the spec and the built RPMs (dnf install rpmlint)
	@# Separate runs: linting a spec and an SRPM together trips an rpmlint state bug.
	cd rpm && $(RPMLINT) --ignore-unused-rpmlintrc -r ansible-collection.rpmlintrc *.spec
	cd rpm && $(RPMLINT) --ignore-unused-rpmlintrc -r ansible-collection.rpmlintrc $(patsubst %,../%,$(wildcard dist/rpm/*.rpm))

version:         ## Set the version in galaxy.yml and the RPM spec: make version V=1.1.0
	@test -n "$(V)" || { echo "usage: make version V=x.y.z"; exit 1; }
	scripts/set-version.sh $(V)

namespace:       ## Rename the collection namespace: make namespace NS=myorg
	@test -n "$(NS)" || { echo "usage: make namespace NS=myorg"; exit 1; }
	scripts/set-namespace.sh $(NS)

clean:           ## Remove build output and caches
	rm -rf dist rpmbuild .pytest_cache .collections .sanity
	find . -name __pycache__ -prune -exec rm -rf {} +
