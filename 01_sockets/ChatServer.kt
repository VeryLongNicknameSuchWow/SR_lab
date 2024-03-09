import java.io.*
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.Executors

class ChatServer(private val port: Int) {
    private val clients = mutableListOf<ClientHandler>()
    private val executor = Executors.newCachedThreadPool()

    fun start() {
        executor.submit { startTcpServer() }
        executor.submit { startUdpServer() }
    }

    private fun startTcpServer() {
        ServerSocket(port).use { tcpServerSocket ->
            println("TCP Server started on port $port...")

            while (true) {
                val clientSocket = tcpServerSocket.accept()
                println("TCP Client connected: ${clientSocket.inetAddress.hostAddress}:${clientSocket.port}")

                val clientHandler = ClientHandler(clientSocket, this)
                executor.submit(clientHandler)
                synchronized(clients) {
                    clients.add(clientHandler)
                }
            }
        }
    }

    private fun startUdpServer() {
        DatagramSocket(port).use { udpServerSocket ->
            println("UDP Server started on port $port...")
            val buffer = ByteArray(1024)
            val packet = DatagramPacket(buffer, buffer.size)

            while (true) {
                udpServerSocket.receive(packet)
                val message = String(packet.data, 0, packet.length).trim()
                val messageBytes = message.toByteArray()
                val echoPacket = DatagramPacket(messageBytes, messageBytes.size)

                synchronized(clients) {
                    clients.filter {
                        it.socket.port != packet.port || it.socket.inetAddress != packet.address
                    }.forEach {
                        udpServerSocket.send(
                            echoPacket.apply {
                                port = it.socket.port
                                address = it.socket.inetAddress
                            }
                        )
                    }
                }
            }
        }
    }

    fun broadcastTcpMessage(message: String, sender: ClientHandler) {
        synchronized(clients) {
            for (client in clients) {
                if (client != sender) {
                    client.sendMessage(message)
                }
            }
        }
    }

    fun removeClient(client: ClientHandler) {
        synchronized(clients) {
            clients.remove(client)
            println("Client disconnected. ${clients.size} client(s) remain.")
        }
    }

    class ClientHandler(val socket: Socket, private val server: ChatServer) : Runnable {
        private val writer: PrintWriter = PrintWriter(socket.getOutputStream(), true)

        override fun run() {
            try {
                BufferedReader(InputStreamReader(socket.getInputStream())).use { reader ->
                    while (true) {
                        val message = reader.readLine()
                        server.broadcastTcpMessage(message, this)
                    }
                }
            } finally {
                server.removeClient(this)
                writer.close()
                socket.close()
            }
        }

        fun sendMessage(message: String) {
            writer.println(message)
        }
    }
}

fun main() {
    val server = ChatServer(9999)
    server.start()
}
