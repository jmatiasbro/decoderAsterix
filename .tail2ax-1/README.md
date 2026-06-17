# tail2ax

Bridge entre Tail y Asterix. Recibe blips modo C y modo S por zmq y genera paquetes ax48.


## Se asume que ...
* Está instalado algún python3 >= 3.6 (como ejemplo asumimos que está instalado python3.6)
* Está instalado el paquete de desarrollo de python3.

Para CentOS: `python3-devel`

Para Ubuntu: `python3-dev`

* Existe un usuario 'administrador' que tiene un /home/administrador


## Crear un virtualenv para python

`administrador@machine: ~/$ python3.6 -m venv ~/venv/tail2ax --symlinks`

`administrador@machine: ~/$ . ~/venv/tail2ax/bin/activate`


va a cambiar el prompt para indicar que el ambiente virtual está activado

`(tail2ax) administrador@machine: ~/$`


ahora actualizar pip (python installer package) e instalar paquete/s

`(tail2ax) administrador@machine: ~/$ pip install --upgrade pip`

`(tail2ax) administrador@machine: ~/$ pip install -r requeriments.txt`

`(tail2ax) administrador@machine: ~/$ deactivate`


y vuelve al prompt original

`administrador@machine: ~/$`



## Probar si arranca el servicio en foreground

`administrador@machine: ~/$ ./tail2axd -fg`

 ó 

`administrador@machine: ~/$ ./tail2axd --foreground`

Debería mostrar el log en pantalla como que arrancó.
Se sale con Ctrl-C



## Probar si arranca el servicio en background

`administrador@machine: ~/$ ./tail2axd start`

Si arranca va a indicar con qué ```pid``` arrancó.

Ejecutar

`administrador@machine: ~/$ ps aux | grep tail2ax`

debería mostrar que hay un proceso corriendo con el ```pid``` que mostró al arrancar.

Para detener el servicio ejecutar

`administrador@machine: ~/$ ./tail2axd stop`

Repetir el comando ```ps```. No debería estar el proceso corriendo.



## Instalar el servicio para que arranque al bootear

Editar el ```contab``` del usuario:

`administrador@machine: ~/$ crontab -e`

agregar una linea con:

`@reboot /home/administrador/tail2ax/tail2axd start`

guardar los cambios y salir.



## Instalar el servicio para que se detenga al apagar la máquina

Ejecutar

`administrador@machine: ~/$ ./install_daemon.sh`

va a pedir password del usuario.

