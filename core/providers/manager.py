import importlib
import pkgutil
from collections.abc import Callable
from typing import Any

from ..logger import Logger


ProviderFactory = Callable[[], Any]


class ProvidersManager:
    def __init__(self):
        self.logger = Logger.get("providers.manager")
        self.providers: dict[str, ProviderFactory] = {}
        self.autoload()

    def autoload(self) -> None:
        package_name = __package__
        if not package_name:
            return

        self.logger.info("providers.autoload.start", package=package_name)

        package = importlib.import_module(package_name)

        for module_info in pkgutil.iter_modules(package.__path__):
            module_name = module_info.name
            if module_name in {"base", "manager"}:
                self.logger.info(
                    "providers.autoload.skip",
                    module=module_name,
                    reason="reserved_module",
                )
                continue
            if module_name.startswith("_"):
                self.logger.info(
                    "providers.autoload.skip",
                    module=module_name,
                    reason="private_module",
                )
                continue

            module_path = f"{package_name}.{module_name}"
            try:
                module = importlib.import_module(module_path)
                provider_name = getattr(module, "PROVIDER_NAME", None)
                create_provider = getattr(module, "create_provider", None)

                if not isinstance(provider_name, str):
                    self.logger.info(
                        "providers.autoload.skip",
                        module=module_name,
                        reason="missing_provider_name",
                    )
                    continue
                if not callable(create_provider):
                    self.logger.info(
                        "providers.autoload.skip",
                        module=module_name,
                        provider=provider_name,
                        reason="missing_factory",
                    )
                    continue
                if provider_name in self.providers:
                    raise ValueError(
                        f"Duplicate provider name '{provider_name}' in module '{module_name}'"
                    )

                self.providers[provider_name] = create_provider
                self.logger.info(
                    "providers.autoload.success",
                    module=module_name,
                    provider=provider_name,
                )
            except Exception as e:
                self.logger.error(
                    "providers.autoload.failure",
                    module=module_name,
                    error=str(e),
                )

        self.logger.info(
            "providers.autoload.complete",
            count=len(self.providers),
            providers=sorted(self.providers),
        )

    def create(self, provider_name: str):
        if provider_name not in self.providers:
            available = ", ".join(sorted(self.providers))
            raise ValueError(
                f"Unsupported provider '{provider_name}'. Available providers: {available}"
            )
        return self.providers[provider_name]()
