# RAG Briefing — nuevo_salesscaling

---

## Objetivos del agente

**Objetivo principal:** Agendar una demo del software con el prospecto.

**Objetivos secundarios:**
- Capturar el email del prospecto para enviar la invitación a la demo.
- Redirigir cualquier pregunta técnica a la reunión.

**KPIs de éxito:**
- Tasa de demos agendadas
- Porcentaje de emails capturados

---

## Candidatos para el RAG (5 documentos)

| # | Nombre | Prioridad | Fuente | Formato sugerido |
|---|--------|-----------|--------|-----------------|
| 1 | Política de Privacidad | Alta | Inferido | `politica_texto` |
| 2 | Integraciones CRM | Alta | Explícito en guion | `FAQ_md` |
| 3 | Información sobre Lanzadera | Media | Explícito en guion | `otro` |
| 4 | Casos de Éxito | Media | Inferido | `otro` |
| 5 | Horarios y Disponibilidad | Baja | Inferido | `otro` |

---

## Fichas detalladas

### 1. Política de Privacidad
**ID:** `politica_privacidad` · **Prioridad:** Alta · **Fuente:** Inferido
**Formato sugerido:** `politica_texto`

**Descripción:** Contiene información sobre cómo se manejan los datos personales y la privacidad.

**¿Por qué lo necesita el agente?** ¿Es seguro / privado?

**Preguntas que respondería este documento:**
- *¿Cómo manejan mis datos?*
- *¿Qué medidas de seguridad tienen?*

### 2. Integraciones CRM
**ID:** `integraciones_crm` · **Prioridad:** Alta · **Fuente:** Explícito en guion
**Formato sugerido:** `FAQ_md`

**Descripción:** Lista de CRMs con los que el software se integra y detalles sobre la API.

**¿Por qué lo necesita el agente?** ¿Se integra con mi CRM?

**Preguntas que respondería este documento:**
- *¿Funciona con Salesforce?*
- *¿Puedo usarlo con Hubspot?*

### 3. Información sobre Lanzadera
**ID:** `informacion_lanzadera` · **Prioridad:** Media · **Fuente:** Explícito en guion
**Formato sugerido:** `otro`

**Descripción:** Detalles sobre la aceleradora Lanzadera y su relación con Sales Scaling.

**¿Por qué lo necesita el agente?** ¿De dónde me llamas? / ¿Cómo se llama tu empresa?

**Preguntas que respondería este documento:**
- *¿Qué es Lanzadera?*
- *¿Cómo está relacionada Sales Scaling con Lanzadera?*

### 4. Casos de Éxito
**ID:** `casos_exito` · **Prioridad:** Media · **Fuente:** Inferido
**Formato sugerido:** `otro`

**Descripción:** Ejemplos de empresas que han mejorado sus ventas usando el software.

**¿Por qué lo necesita el agente?** ¿Cómo puede ayudarme este software?

**Preguntas que respondería este documento:**
- *¿Tienen casos de éxito?*
- *¿Qué empresas han usado su software con éxito?*

### 5. Horarios y Disponibilidad
**ID:** `horarios_disponibilidad` · **Prioridad:** Baja · **Fuente:** Inferido
**Formato sugerido:** `otro`

**Descripción:** Información sobre los horarios disponibles para agendar demos.

**¿Por qué lo necesita el agente?** ¿Cuándo te viene mejor, por la mañana o por la tarde?

**Preguntas que respondería este documento:**
- *¿Qué horarios tienen para demos?*
- *¿Puedo agendar una demo en fin de semana?*
