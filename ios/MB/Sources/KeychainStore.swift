import Foundation
import Security

/// A tiny Keychain wrapper for a single generic-password secret. Used instead of
/// UserDefaults so the user's NIM API key is stored encrypted rather than as
/// plaintext in the app's plist (which lands in unencrypted device backups).
enum Keychain {
  static func read(_ account: String) -> String? {
    let query: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrAccount as String: account,
      kSecReturnData as String: true,
      kSecMatchLimit as String: kSecMatchLimitOne,
    ]
    var item: CFTypeRef?
    guard SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
      let data = item as? Data,
      let value = String(data: data, encoding: .utf8)
    else { return nil }
    return value
  }

  @discardableResult
  static func write(_ value: String, for account: String) -> Bool {
    let base: [String: Any] = [
      kSecClass as String: kSecClassGenericPassword,
      kSecAttrAccount as String: account,
    ]
    // Empty value means "clear the secret".
    guard !value.isEmpty else {
      let status = SecItemDelete(base as CFDictionary)
      return status == errSecSuccess || status == errSecItemNotFound
    }
    let attributes: [String: Any] = [
      kSecValueData as String: Data(value.utf8),
      kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlock,
    ]
    let update = SecItemUpdate(base as CFDictionary, attributes as CFDictionary)
    if update == errSecItemNotFound {
      return SecItemAdd(base.merging(attributes) { $1 } as CFDictionary, nil) == errSecSuccess
    }
    return update == errSecSuccess
  }
}

/// Shared, observable store for the user's secrets. Backs the NIM API key with the
/// Keychain and migrates any key previously saved via @AppStorage (UserDefaults).
@MainActor
final class Secrets: ObservableObject {
  private static let nimKeyAccount = "nim_api_key"

  @Published var nimKey: String {
    didSet { Keychain.write(nimKey, for: Self.nimKeyAccount) }
  }

  init() {
    if let stored = Keychain.read(Self.nimKeyAccount) {
      nimKey = stored
    } else if let legacy = UserDefaults.standard.string(forKey: Self.nimKeyAccount),
      !legacy.isEmpty
    {
      // One-time migration off the old plaintext UserDefaults location.
      nimKey = legacy
      Keychain.write(legacy, for: Self.nimKeyAccount)
      UserDefaults.standard.removeObject(forKey: Self.nimKeyAccount)
    } else {
      nimKey = ""
    }
  }
}
