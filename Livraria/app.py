import sqlite3
from pathlib import Path
import os
import shutil
import csv
from datetime import datetime
import time
import sys

ROOT = Path.cwd() / "meu_sistema_livraria"
DATA_DIR = ROOT / "data"
BACKUP_DIR = ROOT / "backups"
EXPORT_DIR = ROOT / "exports"
DB_FILE = DATA_DIR / "livraria.db"
BACKUP_PREFIX = "backup_livraria_"
MAX_BACKUPS_TO_KEEP = 5
CSV_EXPORT_FILE = EXPORT_DIR / "livros_exportados.csv"
HTML_REPORT_FILE = EXPORT_DIR / "relatorio_livros.html"

def ensure_directories():
    for p in (ROOT, DATA_DIR, BACKUP_DIR, EXPORT_DIR):
        os.makedirs(p, exist_ok=True)

def get_connection():
    return sqlite3.connect(str(DB_FILE))

def init_db():
    ensure_directories()
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS livros (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT NOT NULL,
                ano_publicacao INTEGER,
                preco REAL
            )
        """)
        conn.commit()

def backup_db(reason="manual"):
    ensure_directories()
    if not DB_FILE.exists():
        init_db()
        time.sleep(0.1)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    backup_name = f"{BACKUP_PREFIX}{timestamp}.db"
    backup_path = BACKUP_DIR / backup_name
    shutil.copy2(DB_FILE, backup_path)
    prune_old_backups()
    return backup_path

def prune_old_backups():
    backups = sorted(BACKUP_DIR.glob(f"{BACKUP_PREFIX}*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[MAX_BACKUPS_TO_KEEP:]:
        try:
            old.unlink()
        except Exception:
            pass

def validar_ano(ano_str):
    try:
        ano = int(ano_str)
        if 1000 <= ano <= datetime.now().year + 1:
            return ano
    except:
        pass
    return None

def validar_preco(preco_str):
    try:
        preco = float(preco_str)
        if preco >= 0:
            return preco
    except:
        pass
    return None

def adicionar_livro(titulo, autor, ano_publicacao, preco):
    backup_db(reason="adicionar")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("INSERT INTO livros (titulo, autor, ano_publicacao, preco) VALUES (?, ?, ?, ?)",
                    (titulo.strip(), autor.strip(), ano_publicacao, preco))
        conn.commit()
        return cur.lastrowid

def listar_livros():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, titulo, autor, ano_publicacao, preco FROM livros ORDER BY id")
        return cur.fetchall()

def atualizar_preco_livro(livro_id, novo_preco):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM livros WHERE id = ?", (livro_id,))
        if cur.fetchone() is None:
            return False
    backup_db(reason="atualizar_preco")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE livros SET preco = ? WHERE id = ?", (novo_preco, livro_id))
        conn.commit()
        return cur.rowcount > 0

def remover_livro(livro_id):
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT id FROM livros WHERE id = ?", (livro_id,))
        if cur.fetchone() is None:
            return False
    backup_db(reason="remover")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM livros WHERE id = ?", (livro_id,))
        conn.commit()
        return cur.rowcount > 0

def remover_todos_livros():
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM livros")
        count = cur.fetchone()[0]
        if count == 0:
            return False
    backup_db(reason="remover_todos")
    with get_connection() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM livros")
        conn.commit()
        return True

def buscar_por_autor(autor_query):
    with get_connection() as conn:
        cur = conn.cursor()
        like = f"%{autor_query.strip()}%"
        cur.execute("SELECT id, titulo, autor, ano_publicacao, preco FROM livros WHERE autor LIKE ? ORDER BY id", (like,))
        return cur.fetchall()

def exportar_para_csv(path=CSV_EXPORT_FILE):
    livros = listar_livros()
    ensure_directories()
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["titulo", "autor", "ano_publicacao", "preco"])
        for _id, titulo, autor, ano, preco in livros:
            writer.writerow([titulo, autor, ano if ano is not None else "", preco if preco is not None else ""])
    return path

def importar_de_csv(csv_path):
    if not Path(csv_path).exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {csv_path}")
    inserted = 0
    with open(csv_path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return 0
    backup_db(reason="importar_csv")
    with get_connection() as conn:
        cur = conn.cursor()
        for r in rows:
            titulo = r.get("titulo") or r.get("title") or ""
            autor = r.get("autor") or r.get("author") or ""
            ano_raw = r.get("ano_publicacao") or r.get("year") or ""
            preco_raw = r.get("preco") or r.get("price") or ""
            ano = validar_ano(ano_raw) if ano_raw != "" else None
            preco = validar_preco(preco_raw) if preco_raw != "" else None
            cur.execute("INSERT INTO livros (titulo, autor, ano_publicacao, preco) VALUES (?, ?, ?, ?)",
                        (titulo.strip(), autor.strip(), ano, preco))
            inserted += 1
        conn.commit()
    return inserted

def gerar_relatorio_html(path=HTML_REPORT_FILE):
    livros = listar_livros()
    ensure_directories()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = [
        "<!doctype html>",
        "<html><head><meta charset='utf-8'><title>Relatório de Livros</title>",
        "<style>table{border-collapse:collapse;width:100%}th,td{border:1px solid #ccc;padding:8px;text-align:left}</style>",
        "</head><body>",
        f"<h1>Relatório de Livros</h1><p>Gerado em {now}</p>",
        "<table><thead><tr><th>ID</th><th>Título</th><th>Autor</th><th>Ano</th><th>Preço</th></tr></thead><tbody>"
    ]
    for _id, titulo, autor, ano, preco in livros:
        html.append(f"<tr><td>{_id}</td><td>{titulo}</td><td>{autor}</td><td>{ano or ''}</td><td>{preco if preco is not None else ''}</td></tr>")
    html.append("</tbody></table></body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(html))
    return path

def limpar_tela():
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

def pausa():
    input("\nPressione Enter para continuar...")

def menu():
    init_db()
    while True:
        limpar_tela()
        print("|===========================================|")
        print("|              Livraria Aoros               |")
        print("|===========================================|")
        print("|[1] - Adicionar um Novo Livro              |")
        print("|[2] - Exibir Todos os Livros               |")
        print("|[3] - Atualizar preço de um Livro          |")
        print("|[4] - Remover Livro                        |")
        print("|[5] - Buscar Livros por Autor              |")
        print("|[6] - Exportar dados para CSV              |")
        print("|[7] - Importar dados de CSV                |")
        print("|[8] - Fazer backup manual do banco de dados|")
        print("|[9] - Gerar relatório HTML                 |")
        print("|[10] - Remover TODOS os Livros             |")
        print("|[11] - Sair                                |")
        print("|===========================================|")
        print("|")
        escolha = input("|===== ESCOLHA UMA DAS OPÇÕES ACIMA: ").strip()
        print("")

        if escolha == "1":
            titulo = input("Título: ").strip()
            autor = input("Autor: ").strip()
            ano = None
            while True:
                ano_str = input("Ano de publicação (opcional, ENTER para pular): ").strip()
                if ano_str == "":
                    ano = None
                    break
                ano = validar_ano(ano_str)
                if ano is not None:
                    break
                print("Ano inválido.")
            preco = None
            while True:
                preco_str = input("Preço (ex: 25.50): ").strip()
                if preco_str == "":
                    preco = None
                    break
                preco = validar_preco(preco_str)
                if preco is not None:
                    break
                print("Preço inválido. Informe um número >= 0.")
            if not titulo or not autor:
                print("Título e Autor são obrigatórios.")
                pausa()
                continue
            livro_id = adicionar_livro(titulo, autor, ano, preco)
            print(f"Livro adicionado com id {livro_id}. Backup automático criado.")
            pausa()
        elif escolha == "2":
            livros = listar_livros()
            if not livros:
                print("Nenhum livro cadastrado.")
            else:
                print(f"{'ID':<4} {'Título':<40} {'Autor':<30} {'Ano':<6} {'Preço':>8}")
                print("-"*95)
                for _id, titulo, autor, ano, preco in livros:
                    preco_str = f"R$ {preco:.2f}" if (preco is not None) else ""
                    print(f"{_id:<4} {titulo[:38]:<40} {autor[:28]:<30} {str(ano) if ano else '':<6} {preco_str:>8}")
            pausa()
        elif escolha == "3":
            try:
                livro_id = int(input("ID do livro a atualizar: ").strip())
            except:
                print("ID inválido.")
                pausa()
                continue
            novo_preco = None
            while True:
                preco_str = input("Novo preço: ").strip()
                novo_preco = validar_preco(preco_str)
                if novo_preco is not None:
                    break
                print("Preço inválido.")
            ok = atualizar_preco_livro(livro_id, novo_preco)
            if ok:
                print("Preço atualizado com sucesso. Backup automático criado.")
            else:
                print("Livro não encontrado.")
            pausa()
        elif escolha == "4":
            try:
                livro_id = int(input("ID do livro a remover: ").strip())
            except:
                print("ID inválido.")
                pausa()
                continue
            confirm = input(f"Tem certeza que quer remover o livro {livro_id}? (s/N): ").strip().lower()
            if confirm != "s":
                print("Remoção cancelada.")
                pausa()
                continue
            ok = remover_livro(livro_id)
            if ok:
                print("Livro removido. Backup automático criado.")
            else:
                print("Livro não encontrado.")
            pausa()
        elif escolha == "5":
            autor_q = input("Autor (parte ou nome completo): ").strip()
            if not autor_q:
                print("Pesquisa vazia.")
                pausa()
                continue
            resultados = buscar_por_autor(autor_q)
            if not resultados:
                print("Nenhum livro encontrado para esse autor.")
            else:
                for _id, titulo, autor, ano, preco in resultados:
                    preco_str = f"R$ {preco:.2f}" if (preco is not None) else ""
                    print(f"[{_id}] {titulo} — {autor} ({ano if ano else 'N/A'}) {preco_str}")
            pausa()
        elif escolha == "6":
            path = exportar_para_csv()
            print(f"Exportado para CSV: {path}")
            pausa()
        elif escolha == "7":
            csv_path = input("Caminho do arquivo CSV para importar: ").strip()
            if not csv_path:
                print("Operação cancelada.")
                pausa()
                continue
            try:
                inserted = importar_de_csv(csv_path)
                print(f"Importação concluída. {inserted} registros inseridos. Backup automático criado.")
            except FileNotFoundError as e:
                print(str(e))
            except Exception as e:
                print("Erro ao importar CSV:", e)
            pausa()
        elif escolha == "8":
            bp = backup_db(reason="manual")
            print(f"Backup criado em: {bp}")
            pausa()
        elif escolha == "9":
            path = gerar_relatorio_html()
            print(f"Relatório HTML gerado em: {path}")
            pausa()
        elif escolha == "10":
            confirm = input("⚠ Tem certeza que deseja remover TODOS os livros? (s/N): ").strip().lower()
            if confirm == "s":
                ok = remover_todos_livros()
                if ok:
                    print("✅ Todos os livros foram removidos. Backup automático criado.")
                else:
                    print("⚠ Não havia livros para remover.")
            else:
                print("Operação cancelada.")
            pausa()
        elif escolha == "11":
            print("👋 Saindo do programa...")
            break
        else:
            print("Opção inválida.")
            pausa()

if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print("\nEncerrando (Ctrl+C).")
        sys.exit(0)
