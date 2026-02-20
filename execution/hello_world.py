import os

def main():
    message = "Olá! A arquitetura SDR AGENT está operando corretamente."
    print(message)
    
    # Garante que a pasta .tmp existe
    os.makedirs('.tmp', exist_ok=True)
    
    # Salva o resultado
    with open('.tmp/welcome.txt', 'w', encoding='utf-8') as f:
        f.write(message)
    
    print("Arquivo salvo em .tmp/welcome.txt")

if __name__ == "__main__":
    main()
