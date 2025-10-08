import sys
import pandas as pd

def optimize_schedule(csv_path):
    df = pd.read_csv(csv_path)
    # Exemplo simples de "otimização":
    df['Revisão'] = df['Matéria'] + " - revisar"
    return df

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python optimize_cli.py arquivo.csv")
        sys.exit(1)
    file_path = sys.argv[1]
    result = optimize_schedule(file_path)
    result.to_csv("cronograma_otimizado.csv", index=False)
    print("Cronograma otimizado salvo em cronograma_otimizado.csv")
