/*
 * Controle mínimo do WebKitGTK — o mesmo motor do Safari (WebKit + JavaScriptCore) — para os
 * testes da GALO. A página roda numa janela fora da tela, com perfil efêmero, e recebe
 * cliques e teclas como eventos GDK nativos (os mesmos que o mouse e o teclado produzem).
 *
 * Compilar: gcc -o webkit_driver webkit_driver.c $(pkg-config --cflags --libs webkit2gtk-4.1)
 * Uso:      webkit_driver <endereço> <roteiro.json> <saída.json>
 *
 * O roteiro é uma lista de passos, executados em ordem:
 *   {"avaliar": "<expressão JS>", "nome": "x"}    guarda o valor (JSON) em resultados e valores.x
 *   {"esperar": "<expressão JS>", "limite": 30, "descricao": "..."}   até ser verdadeira
 *   {"clicar": "<seletor CSS>"}                   clique do mouse no centro do elemento
 *   {"digitar": "<texto>"}                        uma tecla por caractere
 *   {"tecla": "Return"}                           uma tecla (nome GDK)
 *   {"pausa": 400}                                espera, em milissegundos
 *   {"abrir": "<endereço>"}                       abre (ou recarrega) uma página
 *   {"dialogos": "aceitar" | "recusar"}           resposta aos próximos confirm()
 * A saída tem o agente (navigator.userAgent), a versão do WebKit, os resultados, os diálogos
 * JS mostrados e o erro, se houver.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <webkit2/webkit2.h>

static WebKitWebView *view;
static GtkWidget *janela;
static JSCContext *js;
static JSCValue *saida, *resultados, *valores, *dialogos;
static int n_resultados, n_dialogos;
static gboolean aceitar_dialogos = TRUE;
static char erro[4096];

/* ------------------------------------------------------------------ espera e avaliação */

static gboolean marcar(gpointer feito) { *(gboolean *)feito = TRUE; return G_SOURCE_REMOVE; }

static void pausa(guint ms) {
    gboolean feito = FALSE;
    g_timeout_add(ms, marcar, &feito);
    while (!feito) g_main_context_iteration(NULL, TRUE);
}

typedef struct { gboolean feito; char *json; char *falha; } Avaliacao;

static void avaliado(GObject *origem, GAsyncResult *res, gpointer dados) {
    Avaliacao *a = dados;
    GError *e = NULL;
    JSCValue *v = webkit_web_view_evaluate_javascript_finish(WEBKIT_WEB_VIEW(origem), res, &e);
    if (e) {
        a->falha = g_strdup(e->message);
        g_error_free(e);
    } else {
        a->json = jsc_value_is_undefined(v) ? g_strdup("null") : jsc_value_to_string(v);
        g_object_unref(v);
    }
    a->feito = TRUE;
}

/* Avalia a expressão na página e devolve o valor em JSON (NULL se falhar; o motivo vai em falha). */
static char *avaliar(const char *expressao, char **falha) {
    char *codigo = g_strdup_printf("JSON.stringify((() => { return (%s); })())", expressao);
    Avaliacao a = { FALSE, NULL, NULL };
    webkit_web_view_evaluate_javascript(view, codigo, -1, NULL, NULL, NULL, avaliado, &a);
    while (!a.feito) g_main_context_iteration(NULL, TRUE);
    g_free(codigo);
    if (falha) *falha = a.falha; else g_free(a.falha);
    if (a.json && strcmp(a.json, "undefined") == 0) { g_free(a.json); a.json = g_strdup("null"); }
    return a.json;
}

static gboolean verdadeiro(const char *json) {
    return json && strcmp(json, "false") && strcmp(json, "null") && strcmp(json, "0") && strcmp(json, "\"\"");
}

static gboolean esperar(const char *expressao, double limite, const char *descricao) {
    gint64 fim = g_get_monotonic_time() + (gint64)(limite * 1e6);
    for (;;) {
        char *falha = NULL;
        char *v = avaliar(expressao, &falha);
        if (g_getenv("GALO_DEPURAR")) fprintf(stderr, "esperar %s -> %s %s\n", expressao, v ? v : "-", falha ? falha : "");
        g_free(falha);
        gboolean ok = verdadeiro(v);
        g_free(v);
        if (ok) return TRUE;
        if (g_get_monotonic_time() > fim) {
            snprintf(erro, sizeof erro, "tempo esgotado esperando %s", descricao ? descricao : expressao);
            return FALSE;
        }
        pausa(100);
    }
}

/* ------------------------------------------------------------------ eventos nativos */

static guint32 agora(void) { return (guint32)(g_get_monotonic_time() / 1000); }

static GdkSeat *assento(void) { return gdk_display_get_default_seat(gdk_display_get_default()); }

static void mouse(GdkEventType tipo, double x, double y) {
    GdkEvent *ev = gdk_event_new(tipo);
    ev->button.window = g_object_ref(gtk_widget_get_window(GTK_WIDGET(view)));
    ev->button.send_event = TRUE;
    ev->button.time = agora();
    ev->button.x = x;
    ev->button.y = y;
    ev->button.x_root = x;
    ev->button.y_root = y;
    ev->button.button = 1;
    ev->button.state = tipo == GDK_BUTTON_RELEASE ? GDK_BUTTON1_MASK : 0;
    gdk_event_set_device(ev, gdk_seat_get_pointer(assento()));
    gtk_widget_event(GTK_WIDGET(view), ev);
    gdk_event_free(ev);
}

static void movimento(double x, double y) {
    GdkEvent *ev = gdk_event_new(GDK_MOTION_NOTIFY);
    ev->motion.window = g_object_ref(gtk_widget_get_window(GTK_WIDGET(view)));
    ev->motion.send_event = TRUE;
    ev->motion.time = agora();
    ev->motion.x = x;
    ev->motion.y = y;
    ev->motion.x_root = x;
    ev->motion.y_root = y;
    gdk_event_set_device(ev, gdk_seat_get_pointer(assento()));
    gtk_widget_event(GTK_WIDGET(view), ev);
    gdk_event_free(ev);
}

static void tecla(GdkEventType tipo, guint valor) {
    GdkEvent *ev = gdk_event_new(tipo);
    ev->key.window = g_object_ref(gtk_widget_get_window(GTK_WIDGET(view)));
    ev->key.send_event = TRUE;
    ev->key.time = agora();
    ev->key.keyval = valor;
    GdkKeymapKey *chaves = NULL;
    gint n = 0;
    if (gdk_keymap_get_entries_for_keyval(gdk_keymap_get_for_display(gdk_display_get_default()), valor, &chaves, &n) && n > 0) {
        ev->key.hardware_keycode = chaves[0].keycode;
        ev->key.group = chaves[0].group;
    }
    g_free(chaves);
    gdk_event_set_device(ev, gdk_seat_get_keyboard(assento()));
    gtk_widget_event(GTK_WIDGET(view), ev);
    gdk_event_free(ev);
}

static void pressionar(guint valor) {
    tecla(GDK_KEY_PRESS, valor);
    tecla(GDK_KEY_RELEASE, valor);
    pausa(25);
}

static gboolean clicar(const char *seletor) {
    JSCValue *s = jsc_value_new_string(js, seletor);
    char *literal = jsc_value_to_json(s, 0);
    char *expr = g_strdup_printf(
        "(() => { const e = document.querySelector(%s); if (!e) return null; e.scrollIntoView({block: 'center'});"
        " const b = e.getBoundingClientRect(); return [b.left + b.width / 2, b.top + b.height / 2]; })()", literal);
    char *json = avaliar(expr, NULL);
    g_free(expr);
    g_free(literal);
    g_object_unref(s);
    JSCValue *pos = json ? jsc_value_new_from_json(js, json) : NULL;
    g_free(json);
    if (!pos || !jsc_value_is_array(pos)) {
        snprintf(erro, sizeof erro, "elemento não encontrado: %s", seletor);
        return FALSE;
    }
    JSCValue *vx = jsc_value_object_get_property_at_index(pos, 0), *vy = jsc_value_object_get_property_at_index(pos, 1);
    double x = jsc_value_to_double(vx), y = jsc_value_to_double(vy);
    g_object_unref(vx);
    g_object_unref(vy);
    g_object_unref(pos);
    gtk_widget_grab_focus(GTK_WIDGET(view));
    movimento(x, y);
    pausa(20);
    mouse(GDK_BUTTON_PRESS, x, y);
    pausa(40);
    mouse(GDK_BUTTON_RELEASE, x, y);
    pausa(120);
    return TRUE;
}

/* ------------------------------------------------------------------ diálogos e saída */

static gboolean dialogo(WebKitWebView *v, WebKitScriptDialog *d, gpointer dados) {
    static const char *tipos[] = { "alert", "confirm", "prompt", "beforeunload" };
    WebKitScriptDialogType t = webkit_script_dialog_get_dialog_type(d);
    JSCValue *par = jsc_value_new_array(js, G_TYPE_NONE);
    JSCValue *tipo = jsc_value_new_string(js, t < 4 ? tipos[t] : "?");
    JSCValue *msg = jsc_value_new_string(js, webkit_script_dialog_get_message(d));
    jsc_value_object_set_property_at_index(par, 0, tipo);
    jsc_value_object_set_property_at_index(par, 1, msg);
    jsc_value_object_set_property_at_index(dialogos, n_dialogos++, par);
    g_object_unref(tipo);
    g_object_unref(msg);
    g_object_unref(par);
    if (t == WEBKIT_SCRIPT_DIALOG_CONFIRM) webkit_script_dialog_confirm_set_confirmed(d, aceitar_dialogos);
    return TRUE;
}

static void definir_texto(JSCValue *obj, const char *nome, const char *texto) {
    JSCValue *v = texto ? jsc_value_new_string(js, texto) : jsc_value_new_null(js);
    jsc_value_object_set_property(obj, nome, v);
    g_object_unref(v);
}

static void gravar_saida(const char *arquivo) {
    if (erro[0]) definir_texto(saida, "erro", erro);
    char *texto = jsc_value_to_json(saida, 0);
    g_file_set_contents(arquivo, texto, -1, NULL);
    g_free(texto);
}

static char *texto_de(JSCValue *passo, const char *nome) {
    JSCValue *v = jsc_value_object_get_property(passo, nome);
    char *t = jsc_value_is_undefined(v) ? NULL : jsc_value_to_string(v);
    g_object_unref(v);
    return t;
}

/* ------------------------------------------------------------------ roteiro */

static gboolean executar_passo(JSCValue *p) {
    char *t;
    if ((t = texto_de(p, "avaliar"))) {
        char *falha = NULL, *json = avaliar(t, &falha);
        g_free(t);
        if (!json) {
            snprintf(erro, sizeof erro, "falha ao avaliar: %s", falha ? falha : "?");
            g_free(falha);
            return FALSE;
        }
        JSCValue *v = jsc_value_new_from_json(js, json);
        g_free(json);
        jsc_value_object_set_property_at_index(resultados, n_resultados++, v);
        char *nome = texto_de(p, "nome");
        if (nome) jsc_value_object_set_property(valores, nome, v);
        g_free(nome);
        g_object_unref(v);
        return TRUE;
    }
    if ((t = texto_de(p, "esperar"))) {
        JSCValue *lim = jsc_value_object_get_property(p, "limite");
        double limite = jsc_value_is_undefined(lim) ? 30 : jsc_value_to_double(lim);
        g_object_unref(lim);
        char *descricao = texto_de(p, "descricao");
        gboolean ok = esperar(t, limite, descricao);
        g_free(descricao);
        g_free(t);
        return ok;
    }
    if ((t = texto_de(p, "clicar"))) {
        gboolean ok = clicar(t);
        g_free(t);
        return ok;
    }
    if ((t = texto_de(p, "digitar"))) {
        for (const char *c = t; *c; c = g_utf8_next_char(c)) pressionar(gdk_unicode_to_keyval(g_utf8_get_char(c)));
        g_free(t);
        return TRUE;
    }
    if ((t = texto_de(p, "tecla"))) {
        guint valor = gdk_keyval_from_name(t);
        g_free(t);
        if (valor == GDK_KEY_VoidSymbol) {
            snprintf(erro, sizeof erro, "tecla desconhecida");
            return FALSE;
        }
        pressionar(valor);
        return TRUE;
    }
    if ((t = texto_de(p, "pausa"))) {
        pausa((guint)atoi(t));
        g_free(t);
        return TRUE;
    }
    if ((t = texto_de(p, "dialogos"))) {
        aceitar_dialogos = strcmp(t, "aceitar") == 0;
        g_free(t);
        return TRUE;
    }
    if ((t = texto_de(p, "abrir"))) {
        g_free(avaliar("window.__galo_pagina_antiga = true", NULL));
        webkit_web_view_load_uri(view, t);
        g_free(t);
        return esperar("!window.__galo_pagina_antiga && document.readyState === 'complete'", 30, "a página abrir");
    }
    snprintf(erro, sizeof erro, "passo desconhecido");
    return FALSE;
}

static gboolean tempo_total(gpointer dados) {
    snprintf(erro, sizeof erro, "tempo total esgotado");
    gravar_saida(dados);
    exit(3);
}

int main(int argc, char **argv) {
    if (argc != 4) {
        fprintf(stderr, "uso: %s <endereço> <roteiro.json> <saída.json>\n", argv[0]);
        return 2;
    }
    /* Janela fora da tela não tem contexto OpenGL: o WebKit desenha por software. */
    g_setenv("WEBKIT_DISABLE_COMPOSITING_MODE", "1", FALSE);
    gtk_init(NULL, NULL);

    WebKitWebContext *contexto = webkit_web_context_new_with_website_data_manager(webkit_website_data_manager_new_ephemeral());
    view = WEBKIT_WEB_VIEW(g_object_new(WEBKIT_TYPE_WEB_VIEW, "web-context", contexto, NULL));
    webkit_settings_set_enable_write_console_messages_to_stdout(webkit_web_view_get_settings(view), TRUE);
    g_signal_connect(view, "script-dialog", G_CALLBACK(dialogo), NULL);
    janela = gtk_offscreen_window_new();
    /* Tamanho fixo na própria vista: a janela fora da tela se ajusta ao tamanho natural do
     * conteúdo, e o balão de validação de formulário do WebKit a encolheria para poucos pixels. */
    gtk_widget_set_size_request(GTK_WIDGET(view), 1100, 800);
    gtk_container_add(GTK_CONTAINER(janela), GTK_WIDGET(view));
    gtk_widget_show_all(janela);

    /* O contexto JSC próprio (para ler o roteiro e montar a saída) só pode ser criado depois da
     * primeira WebView: criado antes, ele inicializa o JavaScriptCore do processo de um jeito
     * que trava a comunicação com o processo da página. */
    js = jsc_context_new();
    char *conteudo = NULL;
    if (!g_file_get_contents(argv[2], &conteudo, NULL, NULL)) {
        fprintf(stderr, "não foi possível ler o roteiro\n");
        return 2;
    }
    JSCValue *roteiro = jsc_value_new_from_json(js, conteudo);
    g_free(conteudo);
    saida = jsc_value_new_object(js, NULL, NULL);
    resultados = jsc_value_new_array(js, G_TYPE_NONE);
    valores = jsc_value_new_object(js, NULL, NULL);
    dialogos = jsc_value_new_array(js, G_TYPE_NONE);
    jsc_value_object_set_property(saida, "resultados", resultados);
    jsc_value_object_set_property(saida, "valores", valores);
    jsc_value_object_set_property(saida, "dialogos", dialogos);
    char *versao = g_strdup_printf("%u.%u.%u", webkit_get_major_version(), webkit_get_minor_version(), webkit_get_micro_version());
    definir_texto(saida, "versao", versao);
    g_free(versao);
    definir_texto(saida, "erro", NULL);

    /* A janela fora da tela nunca recebe foco do sistema: simula a entrada do foco. */
    GdkEvent *foco = gdk_event_new(GDK_FOCUS_CHANGE);
    foco->focus_change.window = g_object_ref(gtk_widget_get_window(janela));
    foco->focus_change.send_event = TRUE;
    foco->focus_change.in = TRUE;
    gtk_widget_send_focus_change(janela, foco);
    gdk_event_free(foco);
    gtk_widget_grab_focus(GTK_WIDGET(view));

    g_timeout_add_seconds(300, tempo_total, argv[3]);
    webkit_web_view_load_uri(view, argv[1]);

    if (esperar("document.readyState === 'complete' && location.href !== 'about:blank'", 30, "a página carregar")) {
        char *agente = avaliar("navigator.userAgent", NULL);
        JSCValue *a = jsc_value_new_from_json(js, agente);
        jsc_value_object_set_property(saida, "agente", a);
        g_object_unref(a);
        g_free(agente);
        JSCValue *tamanho = jsc_value_object_get_property(roteiro, "length");
        int n = jsc_value_to_int32(tamanho);
        g_object_unref(tamanho);
        for (int i = 0; i < n; i++) {
            JSCValue *p = jsc_value_object_get_property_at_index(roteiro, i);
            gboolean ok = executar_passo(p);
            g_object_unref(p);
            if (!ok) {
                char prefixo[64];
                snprintf(prefixo, sizeof prefixo, " (passo %d)", i + 1);
                strncat(erro, prefixo, sizeof erro - strlen(erro) - 1);
                break;
            }
        }
    }
    gravar_saida(argv[3]);
    return 0;
}
