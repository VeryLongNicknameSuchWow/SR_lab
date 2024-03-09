import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.PrintWriter
import java.net.*

fun main(args: Array<String>) {
    val nickname = args[0]

    val host = "127.0.0.1"
    val address = InetAddress.getByName(host)
    val networkInterface = NetworkInterface.getByInetAddress(address)
    val port = 9999
    val tcpSocket = Socket(host, port)
    val udpSocket = DatagramSocket(tcpSocket.localPort)

    val multicastStr = "224.0.0.1"
    val multicastPort = 8888
    val multicastAddress = InetAddress.getByName(multicastStr)
    val multicastSocketAddress = InetSocketAddress(multicastAddress, multicastPort)
    val multicastSocket = MulticastSocket()
    multicastSocket.networkInterface = networkInterface

    try {
        println("Connected to the chat server")

        Thread {
            try {
                BufferedReader(InputStreamReader(tcpSocket.getInputStream())).use {
                    while (true) {
                        val response = it.readLine() ?: break
                        println("[T] $response")
                    }
                }
            } catch (e: Exception) {
                println("Error reading from server: ${e.message}")
            }
        }.start()

        Thread {
            try {
                val buffer = ByteArray(1024)
                val packet = DatagramPacket(buffer, buffer.size)
                while (true) {
                    udpSocket.receive(packet)
                    val response = String(packet.data, 0, packet.length)
                    println("[U] $response")
                }
            } catch (e: Exception) {
                println("Error reading from server: ${e.message}")
            }
        }.start()

        Thread {
            try {
                val buffer = ByteArray(1024)
                val packet = DatagramPacket(buffer, buffer.size)
                MulticastSocket(multicastPort).use {
                    it.joinGroup(multicastSocketAddress, networkInterface)
                    while (true) {
                        it.receive(packet)
                        val response = String(packet.data, 0, packet.length)
                        println("[M] $response")
                    }
                }
            } catch (e: Exception) {
                println("Error reading from server: ${e.message}")
            }
        }.start()

        BufferedReader(InputStreamReader(System.`in`)).use { consoleReader ->
            PrintWriter(tcpSocket.getOutputStream(), true).use { tcpWriter ->
                while (true) {
                    val message = consoleReader.readLine()
                    if (message.startsWith("U ", true)) {
                        val buffer = "$nickname: ${message.substring(2)}".toByteArray()
                        val packet = DatagramPacket(buffer, buffer.size, address, port)
                        udpSocket.send(packet)
                    } else if (message.startsWith("M ", true)) {
                        val buffer = "$nickname: ${message.substring(2)}".toByteArray()
                        val packet = DatagramPacket(buffer, buffer.size, multicastAddress, multicastPort)
                        multicastSocket.send(packet)
                    } else {
                        tcpWriter.println("$nickname: $message")
                    }
                }
            }
        }
    } finally {
        tcpSocket.close()
        udpSocket.close()
        multicastSocket.close()
    }
}
