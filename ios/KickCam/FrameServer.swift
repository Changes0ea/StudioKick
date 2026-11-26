import Foundation
import Network

/// TCP sunucusu: her kareyi [4 bayt big-endian uzunluk][JPEG] olarak bağlı istemcilere gönderir.
/// Bonjour ile "_kickcam._tcp" olarak yayın yapar, Windows uygulaması otomatik bulur.
final class FrameServer {
    private var listener: NWListener?
    private var clients: [ObjectIdentifier: Client] = [:]
    private let queue = DispatchQueue(label: "kickcam.server")
    var onClientsChanged: ((Int) -> Void)?
    /// PC'den gelen JSON mesajları (sohbet vb.), ana thread'de çağrılır.
    var onMessage: (([String: Any]) -> Void)?

    final class Client {
        let conn: NWConnection
        var busy = false
        init(_ c: NWConnection) { conn = c }
    }

    func start(port: UInt16 = 5050, name: String) throws {
        let params = NWParameters.tcp
        params.allowLocalEndpointReuse = true
        if let tcp = params.defaultProtocolStack.transportProtocol as? NWProtocolTCP.Options {
            tcp.noDelay = true
        }
        let l = try NWListener(using: params, on: NWEndpoint.Port(rawValue: port)!)
        l.service = NWListener.Service(name: name, type: "_kickcam._tcp")
        l.newConnectionHandler = { [weak self] conn in self?.accept(conn) }
        l.start(queue: queue)
        listener = l
    }

    func stop() {
        queue.async {
            self.clients.values.forEach { $0.conn.cancel() }
            self.clients.removeAll()
            self.listener?.cancel()
            self.listener = nil
            self.notify()
        }
    }

    private func accept(_ conn: NWConnection) {
        let client = Client(conn)
        let id = ObjectIdentifier(client)
        conn.stateUpdateHandler = { [weak self] state in
            switch state {
            case .failed, .cancelled:
                self?.queue.async { self?.clients[id] = nil; self?.notify() }
            default: break
            }
        }
        clients[id] = client
        conn.start(queue: queue)
        receiveLoop(client)
        notify()
    }

    /// PC -> iPhone: [4 bayt big-endian uzunluk][JSON]
    private func receiveLoop(_ client: Client) {
        client.conn.receive(minimumIncompleteLength: 4, maximumLength: 4) { [weak self] header, _, _, error in
            guard let self, error == nil, let header, header.count == 4 else { return }
            let length = header.reduce(0) { ($0 << 8) | Int($1) }
            guard length > 0, length < 1_000_000 else { client.conn.cancel(); return }
            client.conn.receive(minimumIncompleteLength: length, maximumLength: length) { body, _, _, error in
                if let body,
                   let obj = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
                    DispatchQueue.main.async { self.onMessage?(obj) }
                }
                if error == nil { self.receiveLoop(client) }
            }
        }
    }

    private func notify() {
        let n = clients.count
        DispatchQueue.main.async { self.onClientsChanged?(n) }
    }

    var hasClients: Bool { queue.sync { !clients.isEmpty } }

    /// Kareyi gönder; istemci önceki kareyi henüz almadıysa bu kareyi atla (gecikme birikmesin).
    func send(jpeg: Data) {
        queue.async {
            var header = UInt32(jpeg.count).bigEndian
            var packet = Data(bytes: &header, count: 4)
            packet.append(jpeg)
            for client in self.clients.values where !client.busy {
                client.busy = true
                client.conn.send(content: packet, completion: .contentProcessed { [weak client] err in
                    self.queue.async {
                        client?.busy = false
                        if err != nil { client?.conn.cancel() }
                    }
                })
            }
        }
    }
}
