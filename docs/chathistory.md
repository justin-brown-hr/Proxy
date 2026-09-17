Hola, estas disponible para hablar sobre el proyecto
8:52 AM
Hola, todo bien por acá, disponible sin problema.
8:56 AM
Justo me quedé pensando en tu punto 2, que es donde casi todos se traban.
8:56 AM
Keycloak no trae aprobación manual de fábrica, así que lo limpio es no tocarle el core y manejar a los egresados como un cliente aparte que los crea deshabilitados vía Admin API, y el panel del admin solo les prende el switch.
8:57 AM
Cero parches al gestor, cero dolores de cabeza en el próximo update.
8:57 AM
User Avatar
Alejandro
@alexcd2000
Keycloak no trae aprobación… more
Ok si, entiendo que con esto podriamos unificar usuarios, de diferentes servicios de como microsoft y google?
8:59 AM
Sí, esa es la gracia de Keycloak en el medio. Microsoft entra por OIDC contra Entra ID, Google por el suyo, los dos como IdPs externos en el mismo realm y Nginx solo recibe el token ya validado.
9:11 AM
El truco es el linking por email verificado, así el docente que hoy entra con Google y mañana con la institucional sigue siendo el mismo usuario y no te duplica las métricas.
9:11 AM
User Avatar
Ok, tu has hecho algun desarrollo similar?
9:12 AM
Sí, es terreno conocido. Armé un esquema casi idéntico para acceso a recursos digitales, Nginx con auth_request contra Keycloak y reescritura de URLs para las bases externas, todo dockerizado.
9:15 AM
Lo que más tiempo come no es el proxy, son las particularidades de cada proveedor, algunos validan por IP del servidor y otros te rompen el rewrite con JS embebido. Ahí se gana o se pierde el proyecto.
9:15 AM
Ya tenés la lista de bases de datos que hay que proxear?
9:15 AM
Aun no tengo acceso a las bases de datos, pero no se si podamos replicarlo mientras obtengo los accesos o ir avazandao y es lo que necesitariamos para comenzar a trabajar, asi como tambien cuanto tiempo te tomaria para entragarlo, tomando en cuenta pruebas y documentacion
9:18 AM
User Avatar
De monentto las bases de datos son ScienceDirect, Scopus e IOP, pero quiero que esto quede abierto a poder integrar alguna otra, de manera que sea un desarrollo que pueda escalar mas adelante
9:19 AM
sin problema, no hace falta esperar los accesos para arrancar. El 80% del sistema no depende de ellos, y lo que sí depende lo pruebo contra un recurso dummy que levanto yo mismo simulando el comportamiento de un proveedor real.
9:20 AM
ScienceDirect y Scopus son casi el mismo mundo, así que una vez resuelto Elsevier el segundo sale casi gratis. IOP es más noble.
9:21 AM
para arrancar necesito el dominio o subdominio con su certificado, el acceso al LDAP o Entra, y confirmación del rango de IP institucional. Con eso ya empiezo.
9:21 AM
para este sistema piensas usar un dcoker o directo en server? Puedes decirme los recursos que debo tener para el server
9:24 AM
User Avatar
De comento no tengo el LDAP o Entra, que podemos hacer en ese caso?
9:24 AM
Docker sí o sí, es lo que pide el pliego y además te salva en el handover, tu equipo hace docker compose up y listo, sin rezar para que la versión de Python del server coincida.
9:25 AM
Recursos, para arrancar con 4 vCPU, 8 GB de RAM y 80 GB de disco vas cómodo. La RAM se la come Keycloak con la JVM y Metabase, el proxy en sí es liviano.
9:25 AM
Sobre el LDAP, tranquilo, no bloquea nada
9:26 AM
User Avatar
Alejandro
@alexcd2000
Recursos, para arrancar con 4 vCPU, 8 GB… more
entiendo que esto es para el keycloak y el proxy, o como se va a menjar el acceso a traves de la institucion para acceder a los recursos, ya que no me queda muy claro como se manejaria el tema de las estadisticas de acceso
9:30 AM
El flujo real es este. El usuario no entra a sciencedirect.com, entra a sciencedirect.tudominio.edu. Nginx recibe eso, pregunta a Keycloak si hay sesión válida, si no la hay lo manda a loguearse y vuelve. Recién ahí el proxy sale a buscar el recurso, pero sale con la IP del servidor, que es la que el proveedor tiene en su lista blanca. Para Elsevier siempre es la universidad la que consulta, nunca la casa del alumno. Eso es exactamente lo que hace EZproxy.
9:32 AM
y de ahí sale la estadística sola, porque todo pasa por el proxy. Después de validar, Keycloak me devuelve quién es y con qué rol, y eso lo inyecto en el log de Nginx junto con la URL, el recurso y el tipo de contenido. Un worker lee esos logs, los normaliza y los guarda en una tabla en Postgres, y Metabase se conecta ahí directo. Los gráficos no se programan, se arman sobre esa tabla, y el export a CSV, XML y PDF ya viene incluido.
9:33 AM
Lo lindo es que no dependes de que el proveedor te mande reportes, tenés tu propia verdad.
9:33 AM
😀 👍
9:33 AM
User Avatar
Ok y si yo quisiera replicar esto mismo para otra institucion tendria que desplegar otro server o con ese mismo me serviria?
9:39 AM
Con el mismo server te alcanza, y Keycloak está hecho justo para eso. Cada institución es un realm aparte, con sus usuarios, su LDAP y sus IdPs, totalmente aislados entre sí.
9:40 AM
el límite no es técnico, es de hardware. Con 8 GB metés dos o tres instituciones chicas tranquilo, después es cuestión de sumar RAM o mover Keycloak a su propio nodo. La arquitectura no cambia.
9:40 AM
Ahora, ojo con una cosa, la multiinstitución no está en el alcance actual y meterla completa suma trabajo.
9:41 AM
User Avatar
Entiendo, pero consideras que lo ideal seria aislar cada institicion con su propio sistema keycloak/proxy? o hacerlo multinstitcion?
9:45 AM
Depende de a quién le estés vendiendo, pero mi recomendación honesta va por aislar.
9:46 AM
Mi voto es un stack por institución, pero construido como plantilla desde el día uno.
9:46 AM
User Avatar
Entiendo, entonces por favor dime lo que necesitas para comenzar, cuales serian los detalles de los hitos y los tiempos de entrega de cada fase
9:50 AM
ok
9:53 AM
Perfecto, te lo dejo claro y corto.
Para arrancar necesito tres cosas nada más, el server con Docker instalado y acceso SSH, un dominio o subdominio con wildcard y su certificado, y el rango de IP institucional. El LDAP y las credenciales de Elsevier e IOP los sumamos cuando los tengas, no frenan el arranque.
Los hitos, cinco semanas en total.
Hito 1, semana 1. Stack dockerizado andando, Nginx más Keycloak más Postgres, con SSO funcionando contra un recurso de prueba. Validás entrando con usuario y viendo el acceso pasar.
Hito 2, semanas 2 y 3. El corazón, proxy inverso con rewrite por archivo de configuración, ScienceDirect, Scopus e IOP, más soporte de IP, SAML, CAS, LTI y OAuth. Acá probamos con los accesos reales si ya los tenés, si no contra el simulador.
Hito 3, semana 4. Portal de invitados con autoregistro, estado pendiente y panel de aprobación del admin.
Hito 4, semana 5. Pipeline de logs, tablero en Metabase con clasificación por tipo de contenido y export a CSV, XML y PDF. Cierra con código fuente, imágenes Docker, manual técnico y la sesión grabada de transferencia.
Cada hito se valida y recién ahí pasamos al siguiente, tal cual lo pediste en el post.
Te armo el arranque para el lunes?
10:00 AM
User Avatar
ok dejame te recolecto lo que necesitas
10:10 AM
👍
10:11 AM
User Avatar
listo Alejandro, entonces vamos a preparar los ambientes y te lo pasamos durante el fin de semana para que puedas iniciar el día lunes, procedo a Adjudicar el proyecto a tu persona entonces.
10:22 AM
Vale. Cuál es tu presupuesto para este proyecto?
10:23 AM
User Avatar
bueno tu oferta es de 1,000 dolares correcto?
10:24 AM
Correcto, mil dólares por los cuatro hitos tal como los listé, con el stack dockerizado, la documentación y la sesión de transferencia incluidas.
10:26 AM
Dejo claro solo un punto para que no haya sorpresas después, ese número cubre una institución con las tres bases actuales y la estructura preparada para sumar más. Agregar una base nueva más adelante es trabajo menor, y el multiinstitución completo ya sería otra conversación.
10:27 AM