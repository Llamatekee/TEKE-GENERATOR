# RAG Briefing — nuevo_salesscaling_raw.md

---

## Objetivos del agente

**Objetivo principal:** Detectar interés y agendar demo.

**Objetivos secundarios:**
- Capturar email si no se agenda la demo
- Redirigir preguntas técnicas a la reunión

**KPIs de éxito:**
- Tasa de agendado de demos
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

**Descripción:** Información sobre las integraciones disponibles con CRMs como Salesforce y Hubspot.

**¿Por qué lo necesita el agente?** ¿Se integra con mi CRM?

**Preguntas que respondería este documento:**
- *¿Puedo integrar mi CRM actual?*
- *¿Qué CRMs son compatibles?*

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

**¿Por qué lo necesita el agente?** ¿Cómo ha ayudado a otras empresas?

**Preguntas que respondería este documento:**
- *¿Tienen casos de éxito?*
- *¿Qué resultados han obtenido otros clientes?*

### 5. Horarios y Disponibilidad
**ID:** `horarios_disponibilidad` · **Prioridad:** Baja · **Fuente:** Inferido
**Formato sugerido:** `otro`

**Descripción:** Información sobre los horarios disponibles para agendar demos.

**¿Por qué lo necesita el agente?** ¿Cuándo te viene mejor vernos?

**Preguntas que respondería este documento:**
- *¿Qué horarios tienen disponibles?*
- *¿Puedo agendar una demo por la tarde?*
