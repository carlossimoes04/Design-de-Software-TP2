import sqlite3
from pathlib import Path


class TriageDB:
    def __init__(self, db_path: str = "triagem.db") -> None:
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        with self.conn:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS producoes_locais (
                    telhado_id TEXT NOT NULL,
                    rua_id TEXT NOT NULL,
                    periodo INTEGER NOT NULL,
                    potencia_media_kw REAL NOT NULL,
                    PRIMARY KEY (telhado_id, periodo)
                );

                CREATE TABLE IF NOT EXISTS relatos_locais (
                    relato_id TEXT PRIMARY KEY,
                    telhado_id TEXT NOT NULL,
                    periodo INTEGER NOT NULL,
                    texto TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS triagem_registo (
                    telhado_id TEXT NOT NULL,
                    periodo INTEGER NOT NULL,
                    prompt_enviado TEXT NOT NULL,
                    resposta_bruta TEXT NOT NULL,
                    causa_final TEXT NOT NULL,
                    justificacao TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    PRIMARY KEY (telhado_id, periodo)
                );
                """
            )

    def guardar_producao(
        self, telhado_id: str, rua_id: str, periodo: int, potencia_media_kw: float
    ) -> bool:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO producoes_locais (telhado_id, rua_id, periodo, potencia_media_kw)
                VALUES (?, ?, ?, ?)
                """,
                (telhado_id, rua_id, periodo, potencia_media_kw),
            )
            return cur.rowcount > 0

    def guardar_relato(self, relato_id: str, telhado_id: str, periodo: int, texto: str) -> bool:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO relatos_locais (relato_id, telhado_id, periodo, texto)
                VALUES (?, ?, ?, ?)
                """,
                (relato_id, telhado_id, periodo, texto),
            )
            return cur.rowcount > 0

    def anomalia_ja_tratada(self, telhado_id: str, periodo: int) -> bool:
        row = self.conn.execute(
            "SELECT 1 FROM triagem_registo WHERE telhado_id = ? AND periodo = ?",
            (telhado_id, periodo),
        ).fetchone()
        return row is not None

    def obter_ultimos_periodos_telhado(
        self, telhado_id: str, ate_periodo: int, limite: int = 4
    ) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT periodo, potencia_media_kw
            FROM producoes_locais
            WHERE telhado_id = ? AND periodo <= ?
            ORDER BY periodo DESC
            LIMIT ?
            """,
            (telhado_id, ate_periodo, limite),
        ).fetchall()
        # Devolver por ordem cronológica (mais antigo -> mais recente)
        return [dict(r) for r in reversed(rows)]

    def obter_vizinhos_periodo(self, rua_id: str, telhado_id: str, periodo: int) -> list[dict]:
        rows = self.conn.execute(
            """
            SELECT telhado_id, potencia_media_kw
            FROM producoes_locais
            WHERE rua_id = ? AND periodo = ? AND telhado_id != ?
            ORDER BY telhado_id
            """,
            (rua_id, periodo, telhado_id),
        ).fetchall()
        return [dict(r) for r in rows]

    def obter_relatos_recentes(
        self, telhado_id: str, ate_periodo: int, janela_periodos: int = 4
    ) -> list[dict]:
        desde_periodo = ate_periodo - janela_periodos + 1
        rows = self.conn.execute(
            """
            SELECT relato_id, periodo, texto
            FROM relatos_locais
            WHERE telhado_id = ? AND periodo BETWEEN ? AND ?
            ORDER BY periodo ASC, relato_id ASC
            """,
            (telhado_id, desde_periodo, ate_periodo),
        ).fetchall()
        return [dict(r) for r in rows]

    def guardar_registo_triagem(
        self,
        telhado_id: str,
        periodo: int,
        prompt_enviado: str,
        resposta_bruta: str,
        causa_final: str,
        justificacao: str,
        origem: str,
    ) -> bool:
        with self.conn:
            cur = self.conn.execute(
                """
                INSERT OR IGNORE INTO triagem_registo (
                    telhado_id, periodo, prompt_enviado, resposta_bruta,
                    causa_final, justificacao, origem
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    telhado_id,
                    periodo,
                    prompt_enviado,
                    resposta_bruta,
                    causa_final,
                    justificacao,
                    origem,
                ),
            )
            return cur.rowcount > 0

    def listar_registos(self) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM triagem_registo ORDER BY periodo, telhado_id"
        ).fetchall()
        return [dict(r) for r in rows]

    def close(self) -> None:
        self.conn.close()
