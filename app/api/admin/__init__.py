from fastapi import APIRouter

from app.api.admin import branches, dsas, dtls, roles, users

router = APIRouter(prefix="/api/admin", tags=["admin"])
router.include_router(branches.router)
router.include_router(dtls.router)
router.include_router(dsas.router)
router.include_router(users.router)
router.include_router(roles.router)
