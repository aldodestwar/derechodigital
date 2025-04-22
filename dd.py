import streamlit as st
import google.generativeai as genai
import os
import glob
import time
import textwrap # Keep for shortening long file names if needed

# --- Configuration ---
APP_TITLE = "🏛️ AsesorIA Derecho Digital - Chile" # New Title
DATA_FOLDER = "data"
CONTEXT_FILE_PATTERN = "*.txt"
DISPLAY_MODEL_NAME = "gemini-2.5-flash-preview-04-17" # Updated model name for display
ACTUAL_MODEL_NAME = "gemini-2.5-flash-preview-04-17" # Use the actual model identifier
MAX_CONTEXT_CHARS_WARN = 2000000 # Keep warning for very large context
API_KEY_LINK = "https://aistudio.google.com/apikey"

# --- Initialize session state (remains largely the same) ---
if 'google_api_key' not in st.session_state:
    st.session_state.google_api_key = None
if 'api_key_confirmed' not in st.session_state:
     st.session_state.api_key_confirmed = False
if 'full_context_ready' not in st.session_state:
    st.session_state.full_context_ready = False
    st.session_state.full_text_content = ""
    st.session_state.loaded_files = []
    st.session_state.context_is_large_warning = False
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- Helper Functions ---

@st.cache_data(show_spinner=False)
def load_full_text_from_data(data_dir, file_pattern):
    """Loads and concatenates text from all files in data_dir with st.status animation."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    full_data_path = os.path.join(script_dir, data_dir)
    files = glob.glob(os.path.join(full_data_path, file_pattern))
    all_text = ""
    file_names = []

    if not os.path.exists(full_data_path):
         error_msg = f"❌ **Error Crítico:** La carpeta '{data_dir}' no existe en la ubicación del script (`{script_dir}`). Por favor, créala y coloca tus archivos .txt (leyes digitales) dentro."
         st.error(error_msg)
         return "", [], False, error_msg

    if not files:
        warn_msg = f"⚠️ No se encontraron archivos '{file_pattern}' en la carpeta '{data_dir}'. Asegúrate de que las leyes y normativas (.txt) estén presentes allí."
        # Return warning but allow app to continue (maybe user adds files later)
        return "", [], False, warn_msg

    with st.status("✨ Cargando base de conocimiento legal...", expanded=True) as status:
        total_chars = 0
        errors = []

        for file_path in files:
            file_name = os.path.basename(file_path)
            try:
                content = ""
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                except UnicodeDecodeError:
                    status.update(label=f"⏳ Cargando base de conocimiento... (Intentando latin-1 para {file_name})")
                    with open(file_path, 'r', encoding='latin-1') as f:
                        content = f.read()

                file_names.append(file_name)
                # Add clear markers for each document
                source_marker = f"\n\n--- INICIO DOCUMENTO: {file_name} ---\n\n"
                all_text += source_marker + content
                char_count = len(source_marker) + len(content)
                total_chars += char_count
                status.write(f"📄 Cargado: **{file_name}** ({char_count:,} caracteres)")
                time.sleep(0.05) # Small delay for visual feedback

            except Exception as e:
                error_str = f"❌ Error procesando archivo {file_name}: {e}"
                errors.append(error_str)
                status.write(error_str)

        context_is_large_warning = total_chars > MAX_CONTEXT_CHARS_WARN
        status_message = f"✅ Base de conocimiento legal cargada ({len(file_names)} archivos). Total ~{total_chars:,} caracteres."

        if context_is_large_warning:
             status_message += "\n\n⚠️ **Advertencia:** El contenido total es muy grande. Las respuestas pueden ser más lentas o costosas."

        if errors:
             status_message += f"\n\n❌ Se encontraron {len(errors)} errores al cargar algunos archivos."
             status.update(label="⚠️ Base de conocimiento cargada con errores.", state="warning", expanded=True)
        elif not file_names:
             status.update(label="⚠️ No se encontraron archivos .txt.", state="warning", expanded=True)
        else:
             status.update(label="✅ Base de conocimiento legal cargada.", state="complete", expanded=False)

        return all_text, file_names, context_is_large_warning, status_message


def get_gemini_response_full_context(api_key, full_context, user_query):
    """Generates response using Gemini 1.5 Flash with full context, focused on Digital Law."""
    try:
        genai.configure(api_key=api_key)
    except Exception as e:
        st.error(f"❌ Error configurando Google AI: {e}")
        return "⚠️ Hubo un problema con la configuración de la IA. Verifica tu API Key."

    # --- Modified Prompt for Digital Law Assistant ---
    prompt = f"""**Instrucciones para AsesorIA (Experto en Derecho Digital Chileno):**

Eres un asistente legal experto, especializado en Derecho Digital Chileno. Tu base de conocimiento principal es el material legal proporcionado a continuación. Tu objetivo es analizar, explicar y responder preguntas sobre este material de forma clara, precisa y estructurada, citando las fuentes cuando sea posible.

**Contexto Legal Proporcionado:**
Te proporciono a continuación la **totalidad** del material legal disponible. El material está dividido por documentos, marcados con `--- INICIO DOCUMENTO: [nombre_archivo] ---`.

**Tarea Principal:**
Responde a la *última pregunta del usuario* basándote **principalmente** en la información contenida dentro de **toda** esta base de conocimiento. Puedes comparar y sintetizar información entre los diferentes documentos si es relevante para la pregunta.

**Guías para la Respuesta:**

1.  **Enfoque en el Material:**
    *   Prioriza siempre la información encontrada en los documentos proporcionados.
    *   Si la pregunta se refiere a un tema *dentro* del ámbito del Derecho Digital Chileno pero la información específica *no se encuentra* en los documentos proporcionados, indícalo claramente. Ejemplo: "He revisado los documentos proporcionados ([Lista de archivos relevantes revisados]) y no encuentro detalles específicos sobre [tema de la pregunta]. La legislación incluida no parece abordar ese punto exacto.".
    *   Puedes usar conocimiento general externo de forma muy limitada y solo si es *esencial* para explicar un concepto presente en el material, pero siempre aclara que es contexto general y vuelve al material proporcionado. Tu base principal debe ser el texto dado.

2.  **Formato de Respuesta:**
    *   Organiza tu respuesta de manera lógica y clara.
    *   Utiliza formato Markdown para mejorar la legibilidad: Encabezados (`##`, `###`), listas (`*`, `1.`), **negrita** para términos clave, artículos o leyes importantes.
    *   Sé preciso con la terminología legal encontrada en los textos.

3.  **Citación de Fuentes:**
    *   **Importante:** Siempre que sea posible, después de explicar un punto o al final de secciones relevantes, **indica el documento fuente** entre paréntesis. Ejemplo: `(Fuente: Ley_21180_Transformacion_Digital.txt)`. Si usas varias fuentes, cítalas: `(Fuentes: Ley_19628.txt, Ley_21459.txt)`.

4.  **Comportamiento y Tono:**
    *   Mantén un tono **profesional, objetivo, neutral y servicial**.
    *   Responde de manera respetuosa y directa a la pregunta.
    *   Evita opiniones personales o juicios de valor.

**BASE DE CONOCIMIENTO LEGAL (LEYES DIGITALES CHILENAS):**
{full_context}
--- FIN BASE DE CONOCIMIENTO ---

**ÚLTIMA PREGUNTA DEL USUARIO:**
{user_query}

**TU RESPUESTA (Siguiendo las guías anteriores):**
"""

    try:
        model = genai.GenerativeModel(ACTUAL_MODEL_NAME)
        # Standard safety settings - Keep these as a baseline
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]

        response = model.generate_content(
            prompt,
            safety_settings=safety_settings,
            generation_config=genai.types.GenerationConfig(
                # Adjust temperature if needed, 0.5 is a reasonable default
                temperature=0.5,
                # max_output_tokens=... # Consider setting if facing truncation issues
                )
        )

        # --- Response Handling (Keep the robust error/block handling) ---
        if not response.candidates:
             block_reason = "Desconocida"
             feedback_details = "No disponible"
             if response.prompt_feedback:
                 block_reason = response.prompt_feedback.block_reason or "Desconocida"
                 if response.prompt_feedback.safety_ratings:
                      feedback_details = "; ".join([f"{fb.category.name}: {fb.probability.name}" for fb in response.prompt_feedback.safety_ratings])

             if block_reason == "SAFETY":
                  st.error(f"🔒 La pregunta o la respuesta potencial fue bloqueada por políticas de seguridad. Detalles: {feedback_details}")
                  # Provide a neutral refusal message consistent with the assistant persona
                  return f"⚠️ No puedo procesar esa solicitud, ya que infringe las políticas de seguridad. Por favor, formula una pregunta relacionada con el derecho digital chileno dentro de los marcos apropiados."
             else:
                  st.error(f"🔒 Respuesta bloqueada por la API ({block_reason}). Detalles: {feedback_details}")
                  return f"⚠️ Hubo un problema al generar la respuesta (Bloqueo: {block_reason}). Por favor, intenta reformular tu pregunta."

        candidate = response.candidates[0]
        finish_reason = candidate.finish_reason.name if candidate.finish_reason else "UNKNOWN"

        if candidate.content and candidate.content.parts:
            generated_text = candidate.content.parts[0].text.strip()

            if finish_reason == "SAFETY":
                 st.warning(f"⚠️ La generación de la respuesta se detuvo por: **{finish_reason}**. Mostrando contenido parcial si existe, pero podría ser inapropiado.")
                 return f"⚠️ **Respuesta Bloqueada Parcialmente por Seguridad:**\n\n{generated_text}\n\n*(Advertencia: La respuesta completa fue bloqueada por seguridad. El contenido mostrado puede ser incompleto o problemático.)*"
            elif finish_reason not in ["STOP", "MAX_TOKENS"]:
                st.warning(f"⚠️ La generación de la respuesta se detuvo por: **{finish_reason}**. La respuesta podría estar incompleta.")
                return generated_text + f"\n\n*(Respuesta posiblemente incompleta debido a: {finish_reason})*"
            elif not generated_text:
                 # Empty response
                 return f"⚠️ Ocurrió un problema técnico: la IA generó una respuesta vacía (Razón: {finish_reason})."
            else:
                 # Successful generation
                 return generated_text
        else:
             # No content generated
             return f"⚠️ Ocurrió un problema técnico al generar la respuesta (Razón de finalización: {finish_reason}, sin contenido)."

    # --- Error Handling (Keep the detailed API error handling) ---
    except Exception as e:
        error_str = str(e).lower()
        if "api_key" in error_str or "permission denied" in error_str:
             st.error(f"🔑 Error de API: Clave API inválida, sin permisos para el modelo '{ACTUAL_MODEL_NAME}', o problema de facturación. Verifica tu clave y cuenta de Google AI. ({e})")
             return f"⚠️ **Error de Autenticación/Permiso:** No se pudo acceder al modelo '{ACTUAL_MODEL_NAME}'. Por favor, verifica que tu API Key sea correcta, esté activa y tenga los permisos necesarios. Consulta el enlace en la barra lateral."
        elif "resource_exhausted" in error_str or "quota" in error_str:
             st.error(f"❌ Error de API: Cuota de uso excedida. ({e})")
             return "⚠️ **Error: Límite de Uso Alcanzado.** Has excedido la cuota permitida para la API de Google AI. Inténtalo más tarde o revisa tu plan."
        elif "deadline_exceeded" in error_str:
             st.error(f"⏳ Error de API: Tiempo de espera agotado. El contexto o la pregunta pueden ser demasiado complejos. ({e})")
             return "⚠️ **Error: Tiempo de Espera Excedido.** La solicitud tardó demasiado en procesarse. Esto puede ocurrir con material muy extenso o preguntas muy amplias. Intenta ser más específico/a."
        elif "model_name" in error_str or "not found" in error_str:
             st.error(f"🤖 Error de API: Modelo '{ACTUAL_MODEL_NAME}' no encontrado o inválido. ({e})")
             return f"⚠️ **Error: Modelo No Encontrado.** El modelo '{ACTUAL_MODEL_NAME}' no está disponible o el nombre es incorrecto."
        elif "invalid_argument" in error_str:
             st.error(f"🤔 Error de API: Argumento inválido. Revisa la pregunta o el contexto. ({e})")
             if "safety" in error_str:
                  return "⚠️ **Respuesta Bloqueada:** La solicitud o la respuesta potencial fue bloqueada por las políticas de seguridad. Asegúrate que la pregunta sea apropiada."
             else:
                  return "⚠️ **Error: Solicitud Inválida.** Hubo un problema con los datos enviados a la IA. Intenta reformular tu pregunta."
        else:
            st.error(f"❌ Error inesperado al generar respuesta con Gemini API: {e}")
            return "⚠️ Lo siento, ocurrió un error inesperado al procesar tu solicitud. Por favor, inténtalo de nuevo."


# --- Streamlit App UI (Adjusted for Digital Law) ---
st.set_page_config(page_title=APP_TITLE, layout="wide", initial_sidebar_state="expanded")
st.title(f"{APP_TITLE}") # Use the new title
st.caption(f"Tu asistente IA sobre legislación digital chilena") # New caption
st.markdown(f"🤖 Hola! Soy AsesorIA. Mi conocimiento se basa en las leyes proporcionadas. Pregúntame sobre ellas.") # New initial markdown
st.info(f"🧠 **Modelo IA:** `{DISPLAY_MODEL_NAME}`")


# --- Sidebar Setup (Mostly unchanged, text adjusted) ---
st.sidebar.header("⚙️ Configuración y Estado")
st.sidebar.divider()

# API Key Handling (Unchanged)
st.sidebar.subheader("🔑 API Key de Google Gemini")
if not st.session_state.google_api_key:
    st.sidebar.markdown(f"Necesitas una API Key para usar la IA. Obtenla aquí:")
    st.sidebar.page_link(API_KEY_LINK, label="🔗 Obtener Google API Key", icon="🔑")
    entered_key = st.sidebar.text_input("Ingresa tu Google API Key:", type="password", key="api_key_input", help="Tu clave no se guardará permanentemente.")
    if st.sidebar.button("Confirmar API Key ✨", type="primary"):
        if entered_key:
            st.session_state.google_api_key = entered_key
            st.session_state.api_key_confirmed = True
            try:
                 genai.configure(api_key=st.session_state.google_api_key)
                 # Simple test (optional)
                 # model_check = genai.GenerativeModel(ACTUAL_MODEL_NAME) # Try creating model instance
                 # model_check.generate_content("test", generation_config=genai.types.GenerationConfig(max_output_tokens=5)) # Minimal generation
                 st.sidebar.success("API Key aceptada y configurada. ✅")
                 time.sleep(1)
            except Exception as e:
                 st.sidebar.error(f"Error configurando/verificando Google AI: {e}. Verifica la clave. ❌")
                 st.session_state.google_api_key = None
                 st.session_state.api_key_confirmed = False
            st.rerun()
        else:
            st.sidebar.warning("🚨 Por favor, ingresa una clave API.")
else:
    masked_key = st.session_state.google_api_key[:4] + "****" + st.session_state.google_api_key[-4:]
    st.sidebar.success(f"API Key cargada ({masked_key}). ✅")
    if st.sidebar.button("🗑️ Cambiar/Borrar API Key"):
        # Reset relevant state variables
        keys_to_reset = ['google_api_key', 'api_key_confirmed', 'full_context_ready',
                         'full_text_content', 'loaded_files', 'messages', 'context_is_large_warning']
        for key in keys_to_reset:
            if key in st.session_state: del st.session_state[key]
        st.rerun()

st.sidebar.divider()

# Load Full Text Context after API key confirmation (Unchanged logic, adjusted text)
st.sidebar.subheader("📚 Base de Conocimiento Legal")
if st.session_state.api_key_confirmed and not st.session_state.full_context_ready:
    full_text, loaded_f, is_large, load_status_message = load_full_text_from_data(
        DATA_FOLDER, CONTEXT_FILE_PATTERN
    )
    if "Error Crítico" in load_status_message:
        pass # Error already shown in main area by function
    elif "No se encontraron archivos" in load_status_message:
         st.sidebar.warning(load_status_message)
    elif loaded_f: # Successfully loaded some files
        st.session_state.full_text_content = full_text
        st.session_state.loaded_files = loaded_f
        st.session_state.context_is_large_warning = is_large
        st.session_state.full_context_ready = True
        if "⚠️" in load_status_message: # Handle partial load success with warnings
            st.sidebar.warning(load_status_message)
        else:
            st.sidebar.info(load_status_message) # Show success message

        # Set initial greeting only if messages are empty
        if not st.session_state.messages:
             initial_greeting = f"¡Hola! 👋 Soy tu AsesorIA de Derecho Digital Chileno. He cargado {len(st.session_state.loaded_files)} documento(s) legales: `{', '.join(st.session_state.loaded_files)}`. Mi conocimiento se basa **principalmente** en este material. ¿En qué aspecto de estas leyes te puedo asistir hoy?"
             if st.session_state.context_is_large_warning:
                  initial_greeting += "\n\n*(⚠️ Advertencia: El material es extenso, las respuestas podrían tardar un poco.)*"
             st.session_state.messages.append({"role": "assistant", "content": initial_greeting})
             st.rerun() # Rerun to display the initial message

    elif not loaded_f and not ("Error" in load_status_message or "No se encontraron" in load_status_message):
         # Case where loading function returned empty lists without specific error message
         st.sidebar.error("Ocurrió un error inesperado al cargar los archivos o la carpeta 'data' está vacía.")


# Display loaded files status in sidebar if ready (Unchanged logic)
if st.session_state.full_context_ready and st.session_state.loaded_files:
    st.sidebar.subheader("📄 Leyes Cargadas")
    # Use expander for potentially long list of laws
    with st.sidebar.expander(f"Ver {len(st.session_state.loaded_files)} leyes/documentos", expanded=False):
        for file_name in st.session_state.loaded_files:
            # Shorten long filenames for display
            display_name = textwrap.shorten(file_name, width=35, placeholder="...")
            st.markdown(f"- `{display_name}`")

    if st.session_state.context_is_large_warning:
        st.sidebar.warning("⚠️ El contexto total es muy grande. Podría afectar el rendimiento.")
    else:
         st.sidebar.success("✅ Material legal listo.")


# --- Main Chat Area (Adjusted text) ---
st.divider()

if not st.session_state.google_api_key:
     st.info("👈 Ingresa tu Google API Key en la barra lateral para comenzar. ✨")
elif not st.session_state.full_context_ready:
     if not st.session_state.loaded_files:
         st.warning("⚠️ No se encontraron archivos de leyes en la carpeta 'data'. Por favor, asegúrate de que los archivos .txt estén allí y reinicia la aplicación si es necesario.")
     else:
        st.info("⏳ Esperando la carga del material legal... Revisa la barra lateral para ver el progreso. ✨")
else:
    # Display chat history (Unchanged logic)
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"], unsafe_allow_html=False) # Keep unsafe_allow_html=False

    # Chat input field (Adjusted placeholder)
    if prompt := st.chat_input("Escribe tu consulta sobre Derecho Digital Chileno... 🤔"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Generate and display AI response (Unchanged logic)
        with st.chat_message("assistant"):
             with st.spinner("✨ Analizando la legislación..."):
                 full_response = get_gemini_response_full_context(
                     st.session_state.google_api_key,
                     st.session_state.full_text_content,
                     prompt
                 )
             st.markdown(full_response, unsafe_allow_html=False) # Keep unsafe_allow_html=False

        # Add AI response to state (Unchanged logic)
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        if not full_response.startswith("⚠️"):
            st.rerun() # Rerun on success
        else:
             pass # Don't rerun on error messages to keep them visible

    # Button to clear chat history (Unchanged logic, but keep it)
    if len(st.session_state.messages) > 1: # Show only if there's more than the initial greeting
        st.markdown("---")
        if st.button("🧹 Limpiar Conversación"):
            # Keep initial greeting if it exists
            initial_message = st.session_state.messages[0] if st.session_state.messages and st.session_state.messages[0]['role'] == 'assistant' else None
            st.session_state.messages = [initial_message] if initial_message else []
            st.rerun()


# --- Footer/Notes in Sidebar (Adjusted text) ---
st.sidebar.divider()
st.sidebar.caption("📝 Notas Técnicas:")
st.sidebar.caption(f"IA: `{ACTUAL_MODEL_NAME}`")
st.sidebar.caption("Modo: Contexto Completo (Todo el texto legal de 'data' se envía a la IA).")
st.sidebar.caption("Enfoque: Derecho Digital Chileno según los documentos proporcionados.")
st.sidebar.caption("Puede ser lento/costoso si los archivos .txt son muy grandes.")
st.sidebar.caption("Requiere Google API Key válida.")
st.sidebar.markdown("---")
st.sidebar.caption("✨ App por Aldo Manuel Herrera Hernández - IPP (Adaptado para Derecho Digital)") # Acknowledge adaptation