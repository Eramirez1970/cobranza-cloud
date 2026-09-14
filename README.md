# Bot de Cobranza Automatizada -- Version Cloud Multi-Entidad (Google Sheets + GitHub Actions)

Gestiona cobranza para **varias entidades financieras a la vez**, cada una
con su propio Google Sheet, su propia cartera de deudores, su propia
periodicidad de envio, su propio historial y su propio PDF de evidencia --
todo desde una sola corrida automatica en la nube.

## 1. Arquitectura: un Sheet maestro + un Sheet por entidad

```
Sheet MAESTRO (uno solo)
└── pestana "Entidades": nombre_entidad | sheet_id | activo | notas

Sheet de "Banco Norte" (uno por entidad)
├── Deudores
├── Historial_Envios
├── Parametros          <- periodicidad propia de ESTA entidad
├── Estadisticas_Por_Deudor
├── Resumen_Semanal
└── Resumen_Mensual

Sheet de "Cooperativa Sur" (independiente del anterior)
├── Deudores
├── Historial_Envios
├── Parametros          <- puede tener una periodicidad DISTINTA
└── ... (mismas pestanas)
```

**Por que asi y no todo mezclado en un solo Sheet:** cada entidad financiera
puede necesitar auditar solo su propia cartera -- con Sheets separados,
puedes compartir acceso de solo-lectura a cada una unicamente sobre su
propio Sheet, sin exponer datos de las demas. Ademas, cada entidad puede
tener reglas distintas (ej. una pide notificar diario, otra semanal) y eso
ya queda resuelto porque `Parametros` vive dentro de cada Sheet.

**Agregar una entidad nueva no requiere tocar codigo:** solo agregas una
fila en la pestana "Entidades" del Sheet maestro con el `sheet_id` del
Sheet nuevo (que creaste igual que los demas) y `activo = TRUE`.

## 2. Crear el Sheet MAESTRO

1. Crea una hoja de calculo nueva en Google Sheets -- este es tu panel de control.
2. Se creara sola una pestana "Entidades" la primera vez que corras el
   workflow, con una fila de ejemplo. Reemplazala por tus entidades reales:

   | nombre_entidad | sheet_id | activo | notas |
   |---|---|---|---|
   | Banco Norte | 1AbC...xyz | TRUE | |
   | Cooperativa Sur | 1DeF...uvw | TRUE | |
   | Financiera Andina | 1GhI...rst | FALSE | pausada temporalmente |

3. Copia el ID de este Sheet maestro de su URL -- ese es tu
   `GOOGLE_SHEET_ID_MAESTRO`.
4. **Comparte este Sheet como Editor** con el email de tu Service Account
   (lo tendras a mano despues de correr `setup_workload_identity.sh`,
   seccion 4) -- sin esto, el script no podra leer la lista de entidades.

## 3. Crear un Sheet POR CADA entidad financiera

Repite esto una vez por cada entidad (ver seccion 4 de la version anterior
para el detalle de columnas de "Deudores"):

1. Crea un Google Sheet nuevo, uno exclusivo para esa entidad.
2. Pestana **"Deudores"** con los encabezados:
   ```
   id_cliente | nombre_completo | email | whatsapp | telefono_sms | monto_adeudado |
   moneda | numero_factura | fecha_vencimiento | dias_mora | segmento | canal_enviar |
   estado_gestion | ultimo_contacto | mensaje_enviado | notas
   ```
3. Las pestanas `Parametros`, `Historial_Envios`, `Estadisticas_Por_Deudor`,
   `Resumen_Semanal` y `Resumen_Mensual` se crean solas la primera vez que
   el script procesa esa entidad.
4. Copia el ID de este Sheet y pegalo como `sheet_id` en la fila
   correspondiente del Sheet MAESTRO (paso anterior).
5. **Comparte este Sheet como Editor** con el email de tu Service Account
   (el mismo `SA_EMAIL` que usas en `setup_workload_identity.sh`, seccion
   siguiente) -- sin este paso, esa entidad especifica fallara al procesar
   (aunque las demas seguiran funcionando bien, ver seccion 7).

## 4. Autenticacion: Workload Identity Federation (sin clave JSON)

Si Google Cloud te bloqueo la creacion de claves de Service Account (mensaje
"Se aplicó una política de la organización..."), usa este metodo -- es
ademas el que Google recomienda por seguridad, y no depende de ningun
archivo descargable.

**Que hace:** le da permiso a tu repositorio especifico de GitHub para
"impersonar" tu Service Account directamente durante cada ejecucion del
workflow, sin que exista ninguna clave de por vida guardada en ningun lado.

1. Ve a [console.cloud.google.com](https://console.cloud.google.com), abre
   **Cloud Shell** (icono de terminal arriba a la derecha) -- corre dentro
   del navegador, no instalas nada.
2. Abre el archivo `setup_workload_identity.sh` de este proyecto, copia su
   contenido completo.
3. En Cloud Shell, crea el archivo y pegalo:
   ```bash
   nano setup.sh
   # pega el contenido, Ctrl+O para guardar, Ctrl+X para salir
   ```
4. Edita las 3 variables del inicio del script (`PROJECT_ID`, `SA_EMAIL`,
   `GITHUB_REPO`) con tus datos reales -- `SA_EMAIL` es el de la Service
   Account que ya creaste antes; `GITHUB_REPO` es `tu-usuario/tu-repo` tal
   como aparece en la URL de tu repositorio en GitHub.
5. Corre el script:
   ```bash
   chmod +x setup.sh
   ./setup.sh
   ```
6. Al final te imprime 2 valores -- `GCP_WORKLOAD_IDENTITY_PROVIDER` y
   `GCP_SERVICE_ACCOUNT_EMAIL`. Cópialos, los necesitas en el siguiente paso.

**Nota:** ya NO necesitas generar ni guardar ningun archivo JSON. El secret
`GOOGLE_CREDENTIALS_JSON` puede quedar sin usar -- el codigo ya esta
preparado para detectar automaticamente que estas usando este metodo.

**Importante:** esto NO reemplaza el paso de compartir cada Google Sheet
como Editor con el email de la Service Account (secciones 2 y 3) -- WIF
solo cambia COMO GitHub Actions se autentica como esa Service Account, no
que permisos tiene esa Service Account sobre tus Sheets. Ambos pasos son
necesarios.

## 5. Configurar GitHub

1. Sube el proyecto a un repositorio de GitHub.
2. "Settings" > "Secrets and variables" > "Actions" > "New repository secret":

   | Secret | Valor |
   |---|---|
   | `ANTHROPIC_API_KEY` | tu clave de Claude |
   | `GCP_WORKLOAD_IDENTITY_PROVIDER` | el valor que te imprimio `setup_workload_identity.sh` |
   | `GCP_SERVICE_ACCOUNT_EMAIL` | el email de tu Service Account (mismo script) |
   | `GOOGLE_SHEET_ID_MAESTRO` | el ID del Sheet maestro (NO el de una entidad especifica) |
   | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `EMAIL_REMITENTE` | tus datos de envio de correo |
   | `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_WHATSAPP_FROM`, `TWILIO_SMS_FROM` | tus datos de Twilio |
   | `NOMBRE_EMPRESA` | el nombre de tu emprendimiento (aparece en todos los PDFs) |
   | `MODO_PRUEBA` | `true` para probar, `false` para produccion real |

   Nota: ya NO hay un secret por entidad -- el nombre de cada entidad se
   lee automaticamente de la pestana "Entidades". Tampoco necesitas
   `GOOGLE_CREDENTIALS_JSON` con este metodo de autenticacion.

3. El workflow corre todos los dias; la periodicidad real de cada entidad
   la define su propia hoja `Parametros`.

## 6. Probar antes de ir a produccion -- 100% desde la nube

1. Pestana **"Actions"** de tu repositorio > "Cobranza Automatizada Semanal" > **"Run workflow"**.
2. Con `MODO_PRUEBA=true`, se procesan TODAS las entidades activas, Claude
   genera mensajes reales (centavos), pero el envio se simula.
3. Revisa cada Sheet de entidad (su Historial, sus resumenes) y descarga
   los PDFs generados desde la seccion "Artifacts" de esa ejecucion -- vas
   a encontrar un PDF por cada entidad, nombrado
   `evidencia_cobranza_NombreEntidad_fecha.pdf`.

## 7. Que pasa si una entidad falla

El proceso esta diseñado para que **una entidad con problemas nunca tumbe
a las demas**. Si por ejemplo olvidaste compartir el Sheet de "Cooperativa
Sur" con la Service Account, veras en el log:

```
=== Procesando entidad: Banco Norte ===
  ... (todo OK, PDF generado)

=== Procesando entidad: Cooperativa Sur ===
  [ERROR] Fallo procesando 'Cooperativa Sur': ...

=== Procesando entidad: Financiera Andina ===
  ... (todo OK, PDF generado)

=== RESUMEN GENERAL DE LA CORRIDA ===
Entidades procesadas OK: ['Banco Norte', 'Financiera Andina']
Entidades con error (revisar): ['Cooperativa Sur']
```

Revisas el error puntual de esa entidad sin haber perdido nada de las otras.

## 8. Definir la periodicidad de envio por canal, por entidad

El workflow de GitHub Actions corre **todos los dias** a las 9am -- pero eso
NO significa que se envie algo todos los dias. La periodicidad real la
decide una hoja nueva llamada **"Parametros"**, que funciona como un
formulario: la editas directamente en Google Sheets, sin tocar codigo ni
volver a desplegar nada.

Esta hoja **se crea sola, con valores por defecto**, la primera vez que
corres el workflow. Columnas: `parametro | valor | descripcion`.

| parametro | valor por defecto | que hace |
|---|---|---|
| `activo_email` | TRUE | prende/apaga el canal Email por completo |
| `frecuencia_email` | semanal | diaria / semanal / quincenal / mensual |
| `dias_email` | lunes | dia(s) de envio: nombres (semanal) o numero de dia del mes (quincenal/mensual) |
| `activo_whatsapp` | TRUE | prende/apaga WhatsApp |
| `frecuencia_whatsapp` | semanal | igual patron |
| `dias_whatsapp` | lunes | igual patron |
| `activo_sms` | TRUE | prende/apaga SMS |
| `frecuencia_sms` | mensual | igual patron |
| `dias_sms` | 1 | dia 1 de cada mes |
| `umbral_leve_max` | 30 | hasta cuantos dias de mora es "leve" |
| `umbral_media_max` | 60 | hasta cuantos dias de mora es "media" (mas alla es "critica") |

**Ejemplos de como editarla:**
- Quieres WhatsApp los lunes Y jueves: `dias_whatsapp = lunes,jueves`.
- Quieres SMS quincenal (dias 1 y 15): `frecuencia_sms = quincenal`, `dias_sms = 1,15`.
- Quieres apagar SMS por completo: `activo_sms = FALSE`.
- Quieres que "critica" empiece a los 45 dias en vez de 60: `umbral_media_max = 45`.

Cada corrida diaria lee esta hoja, decide que canal(es) le toca procesar
hoy, y solo notifica a los deudores cuyo canal correspondiente este activo
en ese momento. Los que no les toca hoy quedan `pendiente` y se procesan
automaticamente el dia que si corresponda -- no se pierden ni se duplican.

## 9. Como se resuelve el requisito de "evidencia para la entidad financiera"

- **`Historial_Envios`**: registro append-only, nunca se sobrescribe -- cada
  intento de notificacion (exitoso o fallido) queda como una fila permanente.
  Esta es la fuente de verdad de todo lo demas.
- **`Estadisticas_Por_Deudor`**: se recalcula completa en cada corrida a
  partir del historial -- muestra intentos totales, por canal, tasa de
  exito y estado de cada deudor individual.
- **`Resumen_Semanal`** y **`Resumen_Mensual`**: agregan el historial por
  semana ISO y por mes calendario -- exactamente los 2 cortes de tiempo
  que pediste.
- **PDF de evidencia** (`reportes/evidencia_cobranza_FECHA.pdf`): documento
  formal con ambos resumenes y el detalle por deudor, generado
  automaticamente en cada corrida. En GitHub Actions queda disponible como
  "artefacto descargable" en cada ejecucion (pestana Actions > la corrida >
  seccion Artifacts), listo para enviar a la entidad financiera.

## 10. Estructura del proyecto

```
cobranza_cloud/
├── main.py                    # orquestador: itera entidades activas del Sheet maestro
├── config.py                  # variables de entorno globales
├── parametros.py              # logica de periodicidad (una instancia por entidad)
├── segmentacion.py            # logica leve/media/critica (umbrales por entidad)
├── mensajes_claude.py         # redaccion de mensajes con Claude
├── sheets_client.py           # interaccion con Google Sheets, TODO con sheet_id explicito
├── estadisticas.py            # calculo de resumenes por deudor/semanal/mensual
├── reporte_pdf.py             # genera el PDF de evidencia, uno por entidad
├── canales/
│   ├── email_sender.py
│   ├── whatsapp_sender.py
│   └── sms_sender.py
├── .github/workflows/cobranza.yml   # corre TODOS los dias, itera todas las entidades
├── requirements.txt
├── .env.example
└── README.md
```

## 11. Costos de esta version (recordatorio, MULTIPLICADO por cada entidad activa)

- **GitHub Actions**: $0 (procesar varias entidades en la misma corrida sigue
  usando muy pocos minutos del limite gratis).
- **Google Sheets**: $0, sin importar cuantos Sheets tengas.
- **Claude (Haiku 4.5)**: se multiplica por el volumen TOTAL de deudores de
  todas las entidades juntas -- sigue siendo unos pocos dolares al mes salvo
  que el volumen crezca mucho.
- **Email (SES) y WhatsApp/SMS (Twilio)**: se multiplican por el volumen de
  cada entidad -- si tienes 3 entidades con carteras similares a la que ya
  calculamos, multiplica ese estimado mensual por 3.
