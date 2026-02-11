import oracledb

oracledb.defaults.thin_mode = True


class OracleConnectionManager:
    def __init__(self, settings):
        self.settings = settings
        self.pool: oracledb.AsyncConnectionPool | None = None

    async def create_pool(self) -> oracledb.AsyncConnectionPool:
        params = {
            "user": self.settings.oracle_user,
            "password": self.settings.oracle_password,
            "dsn": self.settings.get_dsn(),
            "min": self.settings.oracle_pool_min,
            "max": self.settings.oracle_pool_max,
        }
        if self.settings.oracle_mode == "adb":
            # Thin mode uses config_dir for ADB mTLS connections
            if self.settings.oracle_wallet_path:
                params["config_dir"] = self.settings.oracle_wallet_path
                params["ssl_server_dn_match"] = True
        self.pool = await oracledb.create_pool_async(**params)
        return self.pool

    async def close_pool(self):
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def get_connection(self):
        return await self.pool.acquire()

    async def release_connection(self, conn):
        await self.pool.release(conn)
