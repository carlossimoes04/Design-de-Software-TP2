import sqlite3
from pathlib import Path


class OperationalDB:
    def __init__(self, db_path: str = "operacional.db") -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS consumos (
                    casa_id TEXT NOT NULL,
                    periodo INTEGER NOT NULL,
                    potencia_media_kw REAL NOT NULL,
                    PRIMARY KEY (casa_id, periodo)
                );

                CREATE TABLE IF NOT EXISTS producoes (
                    telhado_id TEXT NOT NULL,
                    rua_id TEXT NOT NULL,
                    periodo INTEGER NOT NULL,
                    potencia_media_kw REAL NOT NULL,
                    PRIMARY KEY (telhado_id, periodo)
                );

                CREATE TABLE IF NOT EXISTS periodos_fechados (
                    periodo INTEGER PRIMARY KEY,
                    producao_total_kw REAL NOT NULL,
                    consumo_total_kw REAL NOT NULL,
                    saldo_kw REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS medicoes_atrasadas (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tipo TEXT NOT NULL,
                    origem_id TEXT NOT NULL,
                    rua_id TEXT,
                    periodo INTEGER NOT NULL,
                    potencia_media_kw REAL NOT NULL,
                    UNIQUE (tipo, origem_id, periodo)
                );

                CREATE TABLE IF NOT EXISTS estado_sistema (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS acoes_executadas (
                    telhado_id TEXT NOT NULL,
                    periodo INTEGER NOT NULL,
                    causa TEXT NOT NULL,
                    acao TEXT NOT NULL,
                    justificacao TEXT NOT NULL,
                    PRIMARY KEY (telhado_id, periodo)
                );
                """
            )

    def periodo_esta_fechado(self, periodo: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM periodos_fechados WHERE periodo = ?", (periodo,)
        ).fetchone()
        return row is not None

    def guardar_consumo(self, casa_id: str, periodo: int, potencia_media_kw: float) -> bool:
        with self.conn:
            cur = self.conn.execute(
                "INSERT OR IGNORE INTO consumos (casa_id, periodo, potencia_media_kw) VALUES (?, ?, ?)",
                (casa_id, periodo, potencia_media_kw),
            )
            return cur.rowcount > 0

    def guardar_producao(
        self, telhado_id: str, rua_id: str, periodo: int, potencia_media_kw: float
    ) -> bool:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO producoes (telhado_id, rua_id, periodo, potencia_media_kw)
                VALUES (?, ?, ?, ?)
                """,
                (telhado_id, rua_id, periodo, potencia_media_kw),
            )
            return cur.rowcount > 0

    def guardar_medicao_atrasada(
        self,
        tipo: str,
        origem_id: str,
        periodo: int,
        potencia_media_kw: float,
        rua_id: str | None = None,
    ) -> bool:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO medicoes_atrasadas (tipo, origem_id, rua_id, periodo, potencia_media_kw)
                VALUES (?, ?, ?, ?, ?)
                """,
                (tipo, origem_id, rua_id, periodo, potencia_media_kw),
            )
            return cur.rowcount > 0

    def obter_totais_periodo(self, periodo: int) -> tuple[float, float]:
        prod_row = self.conn.execute(
            "SELECT COALESCE(SUM(potencia_media_kw), 0.0) AS total FROM producoes WHERE periodo = ?",
            (periodo,),
        ).fetchone()
        cons_row = self.conn.execute(
            "SELECT COALESCE(SUM(potencia_media_kw), 0.0) AS total FROM consumos WHERE periodo = ?",
            (periodo,),
        ).fetchone()
        return float(prod_row["total"]), float(cons_row["total"])

    def obter_producoes_periodo(self, periodo: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT telhado_id, rua_id, potencia_media_kw FROM producoes WHERE periodo = ? ORDER BY rua_id, telhado_id",
            (periodo,),
        ).fetchall()
        return [dict(r) for r in rows]

    def obter_em_excedente(self) -> bool:
        row = self.conn.execute(
            "SELECT valor FROM estado_sistema WHERE chave = 'em_excedente'"
        ).fetchone()
        return row is not None and row["valor"] == "1"

    def fechar_periodo(
        self,
        periodo: int,
        producao_total_kw: float,
        consumo_total_kw: float,
        saldo_kw: float,
        novo_em_excedente: bool,
    ) -> None:
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO periodos_fechados (periodo, producao_total_kw, consumo_total_kw, saldo_kw)
                VALUES (?, ?, ?, ?)
                """,
                (periodo, producao_total_kw, consumo_total_kw, saldo_kw),
            )
            self.conn.execute(
                """
                INSERT INTO estado_sistema (chave, valor)
                VALUES ('em_excedente', ?)
                ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor
                """,
                ("1" if novo_em_excedente else "0",),
            )

    def registar_acao(
        self, telhado_id: str, periodo: int, causa: str, acao: str, justificacao: str
    ) -> bool:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO acoes_executadas (telhado_id, periodo, causa, acao, justificacao)
                VALUES (?, ?, ?, ?, ?)
                """,
                (telhado_id, periodo, causa, acao, justificacao),
            )
            return cur.rowcount > 0

    def listar_atrasados(self) -> list[dict]:
        rows = self.conn.execute("SELECT * FROM medicoes_atrasadas ORDER BY id").fetchall()
        return [dict(r) for r in rows]

    def obter_saldo_publicado(self, periodo: int) -> dict | None:
        row = self.conn.execute(
            "SELECT * FROM periodos_fechados WHERE periodo = ?", (periodo,)
        ).fetchone()
        return dict(row) if row else None

    def listar_acoes(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM acoes_executadas ORDER BY periodo, telhado_id"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
