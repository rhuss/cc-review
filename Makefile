.PHONY: validate install uninstall reinstall help

MARKETPLACE := cc-review-plugin-development
PLUGIN := cc-review@$(MARKETPLACE)

validate:
	claude plugin validate ./
	claude plugin validate ./review/

install:
	@if claude plugin marketplace add ./ 2>&1 | grep -q "already installed"; then \
		echo "Updating marketplace..."; \
		claude plugin marketplace update $(MARKETPLACE); \
	else \
		echo "Marketplace added."; \
	fi
	@if claude plugin list 2>/dev/null | grep -q "$(PLUGIN)"; then \
		echo "Plugin already installed, reinstalling..."; \
		claude plugin rm $(PLUGIN) 2>/dev/null || true; \
	fi
	claude plugin install $(PLUGIN)

uninstall:
	@echo "Removing plugin..."
	@claude plugin rm $(PLUGIN) 2>/dev/null || echo "Plugin not installed"
	@echo "Removing marketplace..."
	@claude plugin marketplace rm $(MARKETPLACE) 2>/dev/null || echo "Marketplace not installed"

reinstall: uninstall install

help:
	@echo "Available targets:"
	@echo "  validate   - Validate plugin manifests (Claude Code)"
	@echo "  install    - Install plugin via Claude Code marketplace"
	@echo "  uninstall  - Remove plugin and marketplace"
	@echo "  reinstall  - Full uninstall and reinstall"
