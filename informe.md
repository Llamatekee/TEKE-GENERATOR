# Informe de evolución técnica: pipeline de generación de agentes conversacionales

## 1. Objetivo

Este documento resume el paso de un sistema de generación modular fragmentado a una arquitectura unificada y determinista. La nueva herramienta automatiza el saneamiento de los flujos de conversación, eliminando la necesidad de andar retocando el JSON a mano para que el agente funcione correctamente.

## 2. Diagnóstico del estado anterior

Al analizar los workflows que generábamos antes, vimos varios fallos críticos que hacían que los agentes no respondieran bien al importarlos:

- **Configuración global incompleta:** campos clave como `globalIdentity` o `globalInstructions` solían salir vacíos o nulos, lo que dejaba al agente sin una personalidad clara ni instrucciones de qué no debía hacer.
- **Arranque frágil:** el nodo inicial no tenía conectores explícitos ni las variables de inicialización necesarias, por lo que el agente directamente no empezaba a hablar al descolgar.
- **Arquitectura de nodos incoherente:** había fallos entre el tipo de nodo y su clase interna. a veces, nodos que tenían que ramificar estaban marcados como acciones lineales, lo que rompía el flujo.
- **Handles de conexión nulos:** las transiciones lineales se exportaban con el `sourceHandle` vacío, un error estructural que impedía que los cables se dibujaran bien en el dashboard.
- **Exceso de llamadas a la api:** el tener los prompts repartidos por muchos scripts creaba inconsistencias en los nombres de los ids y repetía lógica de forma innecesaria.

## 3. Mejoras de la nueva pipeline

Con la reconstrucción de la herramienta desde cero, hemos implementado soluciones directas para estos problemas:

1. **Orquestador centralizado:** ahora toda la lógica está en un solo sitio, lo que asegura que los ids y los conectores sigan un patrón único y válido por defecto.
2. **Auditoría de grafos (fase 2.5):** he añadido una capa de revisión automática que busca "nodos fantasma" o rutas que se han quedado a medias para arreglarlas antes de generar el archivo final.
3. **Blindaje de identidad:** el sistema ahora fuerza la inyección de la configuración global basándose estrictamente en el manual del cliente, así que el agente es operativo desde el primer segundo.
4. **Soporte para varios documentos:** ahora podemos pasarle el guion, las faqs y los criterios de golpe. esto permite manejar casos complejos como el de luna & wanda sin que se pierda información por el camino.

## 4. Resultados obtenidos

- **Autonomía real:** hemos pasado de un json que no arrancaba a uno que genera agentes listos para hablar (probado ya con linkedupsales y luna & wanda).
- **Estabilidad estructural:** todos los nodos guardan coherencia entre su función y su clase interna, eliminando esos bloqueos visuales en el dashboard.
- **Mejor rendimiento:** al procesar en paralelo y limpiar la lógica de los prompts, hemos reducido las llamadas redundantes a la api y el tiempo de generación.

---

