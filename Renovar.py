import os
import re
import time
import socket
import subprocess
import psutil

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
    WebDriverException,
)

# =========================
# CONFIG LINUX / UBUNTU
# =========================
CHROME_PATH = "/usr/bin/google-chrome"

# Ruta base donde tienes los lotes
BASE_LOTES = "/home/crazy"

# Solo tomará carpetas tipo Facebook-1, Facebook-2, etc.
LOTE_PREFIJO = "Facebook-"

PUERTO_BASE = 9222
DASHBOARD_URL = "https://www.facebook.com/marketplace/you/dashboard?locale=es_LA"
WAIT_SEC = 25


# =========================
# UTILS DE ESCANEO
# =========================
def natural_key(texto):
    partes = re.split(r"(\d+)", texto)
    return [int(p) if p.isdigit() else p.lower() for p in partes]


def listar_lotes(base_lotes):
    if not os.path.exists(base_lotes):
        raise FileNotFoundError(f"No existe BASE_LOTES: {base_lotes}")

    lotes = []
    for nombre in os.listdir(base_lotes):
        ruta = os.path.join(base_lotes, nombre)
        if os.path.isdir(ruta) and nombre.startswith(LOTE_PREFIJO):
            lotes.append(ruta)

    lotes.sort(key=lambda x: natural_key(os.path.basename(x)))
    return lotes


def listar_perfiles_en_lote(ruta_lote):
    perfiles = []
    for nombre in os.listdir(ruta_lote):
        ruta = os.path.join(ruta_lote, nombre)
        if os.path.isdir(ruta):
            perfiles.append(ruta)

    perfiles.sort(key=lambda x: natural_key(os.path.basename(x)))
    return perfiles


def construir_lista_perfiles():
    perfiles_finales = []
    lotes = listar_lotes(BASE_LOTES)

    for lote in lotes:
        perfiles = listar_perfiles_en_lote(lote)
        for perfil in perfiles:
            perfiles_finales.append(perfil)

    return perfiles_finales


# =========================
# UTILS GENERALES
# =========================
def puerto_listo(host="127.0.0.1", port=9222, timeout=20) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


def kill_process_tree(pid: int, timeout=5):
    try:
        parent = psutil.Process(pid)
    except Exception:
        return

    try:
        procs = parent.children(recursive=True) + [parent]
    except Exception:
        procs = [parent]

    for p in procs:
        try:
            if p.is_running():
                p.terminate()
        except Exception:
            pass

    try:
        _, alive = psutil.wait_procs(procs, timeout=timeout)
    except Exception:
        alive = procs

    for p in alive:
        try:
            if p.is_running():
                p.kill()
        except Exception:
            pass


def abrir_con_remote_debug(perfil: str, puerto: int):
    args = [
        CHROME_PATH,
        f"--remote-debugging-port={puerto}",
        f"--user-data-dir={perfil}",
        "--start-maximized",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    return subprocess.Popen(args)


def conectar_selenium(puerto: int):
    options = webdriver.ChromeOptions()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{puerto}")
    options.add_argument("--disable-blink-features=AutomationControlled")

    service = Service()
    driver = webdriver.Chrome(service=service, options=options)
    wait = WebDriverWait(driver, WAIT_SEC)
    return driver, wait


def click_seguro(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.10)
    except Exception:
        pass

    try:
        element.click()
        return True
    except (ElementClickInterceptedException, WebDriverException):
        pass
    except Exception:
        pass

    try:
        ActionChains(driver).move_to_element(element).pause(0.05).click(element).perform()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def esperar_dashboard(wait):
    wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//*[contains(.,'Información general') or contains(.,'Tus publicaciones') or contains(.,'Panel para vendedores')]",
            )
        )
    )


def esperar_dialog(wait):
    return wait.until(EC.presence_of_element_located((By.XPATH, "//div[@role='dialog']")))


def extraer_numero(texto: str) -> int:
    m = re.search(r"(\d+)\+?", texto or "")
    return int(m.group(1)) if m else 0


# =========================
# JS CLICK UNIVERSAL
# =========================
JS_MODAL_CLICK_BY_TEXTS = r"""
(function(texts){
  try{
    const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
    if (!dialogs.length) return {ok:false, reason:"no_dialog"};

    const dialog = dialogs[dialogs.length - 1];

    function findScroller(root){
      const all = Array.from(root.querySelectorAll('div'));
      let best = null;
      let bestH = 0;
      for (const el of all){
        try{
          if (el.scrollHeight > el.clientHeight + 10){
            if (el.clientHeight > bestH){
              bestH = el.clientHeight;
              best = el;
            }
          }
        }catch(e){}
      }
      return best;
    }

    function fireClick(el){
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width/2;
      const cy = rect.top + rect.height/2;
      const opts = {bubbles:true, cancelable:true, view:window, clientX:cx, clientY:cy};
      el.dispatchEvent(new MouseEvent('mouseover', opts));
      el.dispatchEvent(new MouseEvent('mousemove', opts));
      el.dispatchEvent(new MouseEvent('mousedown', opts));
      el.dispatchEvent(new MouseEvent('mouseup', opts));
      el.dispatchEvent(new MouseEvent('click', opts));
    }

    const allNodes = Array.from(dialog.querySelectorAll('*'));
    const hits = [];
    for (const n of allNodes){
      const t = (n.textContent || '').trim();
      if (!t) continue;
      for (const s of texts){
        if (t === s || t.includes(s)){
          hits.push(n);
          break;
        }
      }
    }

    let candidates = [];
    for (const n of hits){
      const c = n.closest('button, [role="button"], [tabindex]');
      if (c) candidates.push(c);
    }
    candidates = Array.from(new Set(candidates));

    let clicked = 0;
    for (const el of candidates){
      try{
        el.scrollIntoView({block:'center'});
        fireClick(el);
        clicked++;
      }catch(e){}
    }

    const scroller = findScroller(dialog) || dialog;

    return {
      ok:true,
      hits:hits.length,
      candidates:candidates.length,
      clicked:clicked,
      scrollerTop:scroller.scrollTop,
      scrollerH:scroller.clientHeight,
      scrollerSH:scroller.scrollHeight
    };
  }catch(e){
    return {ok:false, reason:"exception:" + (e && e.message ? e.message : String(e))};
  }
})
"""

JS_MODAL_SCROLL = r"""
(function(){
  try{
    const dialogs = Array.from(document.querySelectorAll('div[role="dialog"]'));
    if (!dialogs.length) return {ok:false, reason:"no_dialog"};
    const dialog = dialogs[dialogs.length - 1];

    function findScroller(root){
      const all = Array.from(root.querySelectorAll('div'));
      let best = null;
      let bestH = 0;
      for (const el of all){
        try{
          if (el.scrollHeight > el.clientHeight + 10){
            if (el.clientHeight > bestH){
              bestH = el.clientHeight;
              best = el;
            }
          }
        }catch(e){}
      }
      return best;
    }

    const scroller = findScroller(dialog) || dialog;
    const before = scroller.scrollTop;
    scroller.scrollTop = scroller.scrollTop + scroller.clientHeight;
    const after = scroller.scrollTop;

    return {ok:true, before:before, after:after, h:scroller.clientHeight, sh:scroller.scrollHeight};
  }catch(e){
    return {ok:false, reason:"exception:" + (e && e.message ? e.message : String(e))};
  }
})()
"""


def js_click_texts(driver, texts):
    try:
        res = driver.execute_script("return (" + JS_MODAL_CLICK_BY_TEXTS + ")(arguments[0]);", texts)
    except Exception as e:
        return {"ok": False, "reason": f"js_exception:{type(e).__name__}:{e}"}

    if not isinstance(res, dict):
        return {"ok": False, "reason": f"js_return_not_dict:{repr(res)}"}
    return res


def js_scroll_modal(driver):
    try:
        res = driver.execute_script("return " + JS_MODAL_SCROLL)
    except Exception as e:
        return {"ok": False, "reason": f"scroll_exception:{type(e).__name__}:{e}"}
    if not isinstance(res, dict):
        return {"ok": False, "reason": f"scroll_return_not_dict:{repr(res)}"}
    return res


# =========================
# 1) RENOVAR
# =========================
def leer_para_renovar(driver, wait) -> int:
    tile = wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//*[normalize-space()='Para renovar']/ancestor::*[@role='button' or self::a][1]",
            )
        )
    )
    return extraer_numero(tile.text.strip())


def abrir_modal_para_renovar(driver, wait):
    tile = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[normalize-space()='Para renovar']/ancestor::*[@role='button' or self::a][1]",
            )
        )
    )
    click_seguro(driver, tile)
    dialog = esperar_dialog(wait)

    try:
        wait.until(
            EC.presence_of_element_located(
                (
                    By.XPATH,
                    "//div[@role='dialog']//*[contains(normalize-space(),'Renovar') or contains(normalize-space(),'publicaciones')]",
                )
            )
        )
    except TimeoutException:
        pass

    return dialog


def renovar_todo_en_modal(driver, wait, max_rounds=80) -> int:
    total = 0
    sin_click = 0

    esperar_dialog(wait)
    time.sleep(0.6)

    for r in range(1, max_rounds + 1):
        info = js_click_texts(driver, ["Renovar"])
        if not info.get("ok"):
            print(f"   [RENOVAR] JS no pudo: {info}")
            js_scroll_modal(driver)
            time.sleep(0.6)
            sin_click += 1
            if sin_click >= 6:
                break
            continue

        clicked = int(info.get("clicked", 0) or 0)
        hits = int(info.get("hits", 0) or 0)
        cands = int(info.get("candidates", 0) or 0)

        print(f"   [RENOVAR] Ronda {r} | hits={hits} | candidatos={cands} | clicked={clicked}")
        total += clicked

        if clicked == 0:
            sin_click += 1
            js_scroll_modal(driver)
            time.sleep(0.6)
        else:
            sin_click = 0
            time.sleep(0.35)

        if sin_click >= 10:
            break

    try:
        listo = WebDriverWait(driver, 6).until(
            EC.element_to_be_clickable(
                (
                    By.XPATH,
                    "//div[@role='dialog']//*[@role='button' and normalize-space()='Listo']"
                    " | //div[@role='dialog']//button[normalize-space()='Listo']",
                )
            )
        )
        click_seguro(driver, listo)
    except Exception:
        try:
            driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except Exception:
            pass

    return total


def proceso_para_renovar(driver, wait):
    while True:
        val = leer_para_renovar(driver, wait)
        print(f"   [RENOVAR] Para renovar = {val}")

        if val == 0:
            print("   ➡️ [RENOVAR] Ya está en 0.")
            return

        abrir_modal_para_renovar(driver, wait)
        clicks = renovar_todo_en_modal(driver, wait)
        print(f"   ✅ [RENOVAR] Clicks total en modal: {clicks}")

        if clicks == 0:
            print("   ⚠️ [RENOVAR] 0 clicks. Salgo de RENOVAR.")
            return

        time.sleep(0.8)
        driver.get(DASHBOARD_URL)
        esperar_dashboard(wait)
        time.sleep(0.6)


# =========================
# 2) ELIMINAR Y REPUBLICAR
# =========================
def leer_para_eliminar(driver, wait) -> int:
    tile = wait.until(
        EC.presence_of_element_located(
            (
                By.XPATH,
                "//*[normalize-space()='Para eliminar y volver a publicar']/ancestor::*[@role='button' or self::a][1]",
            )
        )
    )
    return extraer_numero(tile.text.strip())


def cerrar_modal(driver):
    try:
        dialog = driver.find_element(By.XPATH, "//div[@role='dialog']")
    except Exception:
        return

    try:
        x = dialog.find_element(By.XPATH, ".//*[@aria-label='Cerrar' or @aria-label='Close']")
        click_seguro(driver, x)
        time.sleep(0.4)
        return
    except Exception:
        pass

    try:
        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        time.sleep(0.4)
    except Exception:
        pass


def cerrar_modal_si_no_hay_mas(driver) -> bool:
    try:
        dialog = driver.find_element(By.XPATH, "//div[@role='dialog']")
        txt = dialog.text or ""
        frases = [
            "No tienes más publicaciones",
            "que puedan eliminarse",
            "volver a realizarse",
            "puedan eliminarse y volver",
        ]
        if any(f in txt for f in frases):
            cerrar_modal(driver)
            return True
    except Exception:
        pass
    return False


def abrir_modal_para_eliminar(driver, wait) -> bool:
    tile = wait.until(
        EC.element_to_be_clickable(
            (
                By.XPATH,
                "//*[normalize-space()='Para eliminar y volver a publicar']/ancestor::*[@role='button' or self::a][1]",
            )
        )
    )
    click_seguro(driver, tile)
    esperar_dialog(wait)

    if cerrar_modal_si_no_hay_mas(driver):
        print("   ℹ️ [ELIMINAR] No hay más publicaciones en el modal. Cerrado.")
        return False

    return True


def click_eliminar_y_republicar_todos(driver, wait) -> bool:
    if cerrar_modal_si_no_hay_mas(driver):
        return False

    esperar_dialog(wait)
    time.sleep(0.8)

    targets_main = [
        "Eliminar y volver a publicar todos",
        "Eliminar y volver a publicar",
        "Volver a publicar",
    ]
    info = js_click_texts(driver, targets_main)
    if not info.get("ok"):
        print(f"   [ELIMINAR] JS no pudo (principal): {info}")
        return False

    print(f"   [ELIMINAR] Principal | hits={info.get('hits')} cand={info.get('candidates')} clicked={info.get('clicked')}")
    if int(info.get("clicked", 0) or 0) == 0:
        js_scroll_modal(driver)
        time.sleep(0.8)
        info2 = js_click_texts(driver, targets_main)
        print(f"   [ELIMINAR] Reintento principal | clicked={info2.get('clicked')}")
        if not info2.get("ok") or int(info2.get("clicked", 0) or 0) == 0:
            return False

    time.sleep(1.0)

    conf = js_click_texts(driver, ["Confirmar", "Aceptar", "Eliminar"])
    if conf.get("ok") and int(conf.get("clicked", 0) or 0) > 0:
        print(f"   [ELIMINAR] Confirmación clicked={conf.get('clicked')}")
        time.sleep(1.0)

    listo = js_click_texts(driver, ["Listo"])
    if listo.get("ok") and int(listo.get("clicked", 0) or 0) > 0:
        print("   [ELIMINAR] Click 'Listo'")
        time.sleep(0.8)
    else:
        cerrar_modal(driver)

    return True


def proceso_para_eliminar(driver, wait):
    sin_avance = 0
    ultimo_val = None

    while True:
        val = leer_para_eliminar(driver, wait)
        print(f"   [ELIMINAR] Para eliminar y volver a publicar = {val}")

        if val == 0:
            print("   ➡️ [ELIMINAR] Ya está en 0.")
            return

        if ultimo_val is not None and val == ultimo_val:
            sin_avance += 1
        else:
            sin_avance = 0
        ultimo_val = val

        if sin_avance >= 3:
            print("   ⚠️ [ELIMINAR] El contador no baja. Salgo para evitar bucle.")
            return

        ok_modal = abrir_modal_para_eliminar(driver, wait)
        if not ok_modal:
            driver.get(DASHBOARD_URL)
            esperar_dashboard(wait)
            time.sleep(0.6)
            continue

        ok = click_eliminar_y_republicar_todos(driver, wait)
        if not ok:
            print("   ℹ️ [ELIMINAR] No se pudo ejecutar (o ya no hay más).")
            cerrar_modal(driver)
            return

        time.sleep(0.8)
        driver.get(DASHBOARD_URL)
        esperar_dashboard(wait)
        time.sleep(0.6)


# =========================
# MAIN
# =========================
def main():
    if not os.path.exists(CHROME_PATH):
        raise FileNotFoundError(f"No existe CHROME_PATH: {CHROME_PATH}")

    perfiles = construir_lista_perfiles()

    if not perfiles:
        raise RuntimeError(f"No se encontraron perfiles dentro de {BASE_LOTES}")

    print("\n==============================")
    print("PERFILES ENCONTRADOS:")
    for i, p in enumerate(perfiles, start=1):
        print(f"[{i}] {p}")
    print("==============================\n")

    for idx, perfil in enumerate(perfiles, start=1):
        if not os.path.exists(perfil):
            print("\n==============================")
            print(f"[PERFIL {idx}] ❌ Carpeta no existe → {perfil}")
            print(f"[PERFIL {idx}] ⏭ Saltando perfil...")
            continue

        puerto = PUERTO_BASE + (idx - 1)

        print("\n==============================")
        print(f"[PERFIL {idx}] Abriendo Chrome: {perfil}")
        print(f"[PERFIL {idx}] Puerto asignado: {puerto}")

        chrome_proc = abrir_con_remote_debug(perfil, puerto)
        driver = None

        try:
            print(f"[PERFIL {idx}] Esperando puerto {puerto}...")
            if not puerto_listo(port=puerto, timeout=25):
                print(f"❌ [PERFIL {idx}] Puerto no listo. Cerrando.")
                kill_process_tree(chrome_proc.pid)
                continue

            driver, wait = conectar_selenium(puerto)

            driver.get(DASHBOARD_URL)
            esperar_dashboard(wait)
            time.sleep(0.8)

            print(f"[PERFIL {idx}] Ejecutando: PARA RENOVAR")
            proceso_para_renovar(driver, wait)

            print(f"[PERFIL {idx}] Ejecutando: PARA ELIMINAR Y VOLVER A PUBLICAR")
            driver.get(DASHBOARD_URL)
            esperar_dashboard(wait)
            time.sleep(0.8)
            proceso_para_eliminar(driver, wait)

            print(f"[PERFIL {idx}] ✅ Terminado (renovar + eliminar/republicar).")

        except Exception as e:
            print(f"❌ [PERFIL {idx}] FALLÓ con error:")
            print(repr(e))

        finally:
            try:
                if driver:
                    driver.quit()
            except Exception:
                pass

            try:
                kill_process_tree(chrome_proc.pid)
            except Exception:
                pass


if __name__ == "__main__":
    main()
