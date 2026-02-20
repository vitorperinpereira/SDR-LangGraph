import asyncio
import logging

from app.services.evolution_service import EvolutionService
from app.services.redis_service import RedisService
from app.services.supabase_service import SupabaseService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("phase1_services_check")


async def main() -> None:
    redis_service = RedisService()
    supabase_service = SupabaseService()
    evolution_service = EvolutionService()

    redis_ok = await redis_service.check_connection()
    if redis_ok:
        logger.info("Redis connection: OK")
    else:
        logger.info("Redis connection: skipped or unavailable (running with fallback)")

    supabase_ok = await supabase_service.check_connection()
    if supabase_ok:
        logger.info("Supabase connection: OK")
    else:
        logger.info("Supabase connection: skipped or unavailable")

    evolution_ok = await evolution_service.check_connection()
    if evolution_ok:
        logger.info("Evolution connection: OK")
    else:
        logger.info("Evolution connection: skipped or unavailable")

    # Debounce smoke check (works in Redis or fallback memory mode).
    first_try = await redis_service.acquire_debounce_lock("phase1-smoke")
    second_try = await redis_service.acquire_debounce_lock("phase1-smoke")
    logger.info("Redis debounce smoke check: first=%s second=%s", first_try, second_try)

    await redis_service.close()


if __name__ == "__main__":
    asyncio.run(main())
