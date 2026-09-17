Buscamos un Desarrollador Senior para construir una solución propia de Proxy Inverso y Autenticación Unificada orientada a bibliotecas universitarias. El sistema debe basarse en tecnologías Open Source y entregarse completamente dockerizado y documentado. En esencia, lo que se busca es replicar la funcionalidad principal que realiza EZproxy para gestionar y facilitar los accesos remotos e internos a los recursos y bases de datos digitales de la universidad.

Esta no es una web tradicional; es un proyecto de infraestructura, redes, seguridad y gestión de identidades.

Requerimientos Técnicos y Alcance:
1. Proxy Inverso: Servidor (Nginx u otro) capaz de reescribir URLs y dar acceso remoto a bases de datos de investigación.
2. Autenticación (SSO): Integración con un Identity Provider (ej. Keycloak) que soporte IP, LDAP, SAML 2.0, CAS, LTI (Canvas/Moodle), OAuth2 y OpenID Connect.
3. Módulo de Invitados: Desarrollo de un portal ligero donde usuarios externos (egresados/invitados) realicen un auto-registro, quedando en estado "pendiente" hasta que un administrador los apruebe desde un panel.
4. Dashboard de Analíticas: Pipeline que lea los logs del proxy, los procese y los envíe a una herramienta BI (ej. Metabase/Grafana) para clasificar los accesos en distintos tipos de contenidos (ej. PDF, videos, artículos) y permita exportar en CSV, XML y PDF.

Condiciones y Entregables:
• Presupuesto total: $1,400 USD.
• Tiempo estimado: 4 a 6 semanas.
• Modalidad de pago: Estrictamente por hitos funcionales y validados.
• Handover: El último hito exige la entrega del código fuente, imágenes Docker, manual técnico detallado y una sesión grabada de transferencia de conocimiento a nuestro equipo in-house.

¿CÓMO POSTULAR? (LEER ATENTAMENTE)
Para que tu propuesta sea leída, debes responder estas 3 preguntas en tu mensaje de postulación:
1. ¿Qué herramienta de código abierto usarías como Identity Provider y cómo harías para que Nginx se comunique con ella antes de dejar pasar al usuario?
2. Si usamos un sistema centralizado como Keycloak, ¿cómo programarías el flujo del módulo de invitados (auto-registro con aprobación manual) sin alterar el core del gestor?
3. ¿Cómo diseñarías la arquitectura de datos para procesar los logs de Nginx y mostrar las estadísticas en un panel exportable a PDF sin programar los gráficos desde cero?