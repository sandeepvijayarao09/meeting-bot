import Foundation

/// Transcript refinement tier, mirroring `config.REFINE` on the Python side.
public enum RefineTier: String, Sendable {
  case off
  case local
  case cloud
}

/// On-device speech-to-text. The concrete implementation (WhisperKit) lives in the
/// app target so this package stays dependency-free and unit-testable.
public protocol ASRProvider: Sendable {
  /// Transcribe one 16 kHz mono WAV file into plain text.
  func transcribe(_ wav: URL) async throws -> String
}

/// A chat-completion backend (on-device Gemma, or the NVIDIA NIM cloud fallback).
public protocol LLMProvider: Sendable {
  func complete(system: String, user: String, maxTokens: Int) async throws -> String
}

public enum LLMError: Error, Equatable {
  case missingKey
  case badURL
  case badResponse
  case http(Int, String)
  /// The on-device model (or its runtime) isn't available yet — callers fall back
  /// to a transcript-only note rather than failing. Used by `GemmaProvider`.
  case modelUnavailable
}

/// NVIDIA NIM (OpenAI-compatible) chat completions over URLSession — the Swift
/// port of `meetingbot/summarize.complete`. Used as the cloud fallback on iOS when
/// the device can't run on-device Gemma (or before the model is downloaded).
public struct NIMProvider: LLMProvider {
  public let apiKey: String
  public let baseURL: String
  public let model: String

  public init(
    apiKey: String,
    baseURL: String = "https://integrate.api.nvidia.com/v1",
    model: String = "openai/gpt-oss-120b"
  ) {
    self.apiKey = apiKey
    self.baseURL = baseURL
    self.model = model
  }

  public func complete(system: String, user: String, maxTokens: Int = 4096) async throws -> String {
    guard !apiKey.isEmpty else { throw LLMError.missingKey }
    guard let url = URL(string: baseURL + "/chat/completions") else { throw LLMError.badURL }

    var request = URLRequest(url: url)
    request.httpMethod = "POST"
    request.setValue("Bearer \(apiKey)", forHTTPHeaderField: "Authorization")
    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
    let payload: [String: Any] = [
      "model": model,
      "messages": [
        ["role": "system", "content": system],
        ["role": "user", "content": user],
      ],
      "temperature": 0.2,
      "max_tokens": maxTokens,
    ]
    request.httpBody = try JSONSerialization.data(withJSONObject: payload)

    let (data, response) = try await URLSession.shared.data(for: request)
    guard let http = response as? HTTPURLResponse else { throw LLMError.badResponse }
    guard (200..<300).contains(http.statusCode) else {
      throw LLMError.http(http.statusCode, String(data: data, encoding: .utf8) ?? "")
    }
    guard
      let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
      let choices = object["choices"] as? [[String: Any]],
      let message = choices.first?["message"] as? [String: Any],
      let content = message["content"] as? String
    else { throw LLMError.badResponse }
    return content.trimmingCharacters(in: .whitespacesAndNewlines)
  }
}
