import time, sys

INTENTOS_ARCHIVO = "test_crash_count.txt"

# Leer cuántas veces crasheó ya
try:
    with open(INTENTOS_ARCHIVO) as f:
        n = int(f.read().strip())
except FileNotFoundError:
    n = 0

n += 1
with open(INTENTOS_ARCHIVO, "w") as f:
    f.write(str(n))

print(f"App simulada: intento #{n}")
time.sleep(2)

if n < 3:
    print(f"App simulada: CRASH simulado (intento {n}/3)")
    sys.exit(1)   # <-- crash

print("App simulada: arranque exitoso en intento 3. Cerrando normalmente.")
time.sleep(3)
sys.exit(0)       # <-- cierre limpio al 3er intento
