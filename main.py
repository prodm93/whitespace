"""Dev entrypoint — thin wiring layer only."""

import logging

from whitespace.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)


def main() -> None:
    config = Config()
    logger.info("WhiteSpace starting in %s mode", config.mode)


if __name__ == "__main__":
    main()
