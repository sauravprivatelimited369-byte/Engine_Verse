import MeridianCore
import SwiftUI

struct MeridianPalette {
    let background: Color
    let surface: Color
    let surfaceVariant: Color
    let primary: Color
    let primaryContainer: Color
    let onPrimaryContainer: Color
    let ink: Color
    let mutedInk: Color
    let border: Color
    let ok: Color

    static let light = MeridianPalette(
        background: Color(red: 0xF5 / 255.0, green: 0xF2 / 255.0, blue: 0xEA / 255.0),
        surface: Color(red: 0xFB / 255.0, green: 0xF9 / 255.0, blue: 0xF4 / 255.0),
        surfaceVariant: Color(red: 0xE8 / 255.0, green: 0xE4 / 255.0, blue: 0xD9 / 255.0),
        primary: Color(red: 0x1D / 255.0, green: 0x5B / 255.0, blue: 0xD6 / 255.0),
        primaryContainer: Color(red: 0xDC / 255.0, green: 0xE7 / 255.0, blue: 0xFB / 255.0),
        onPrimaryContainer: Color(red: 0x0A / 255.0, green: 0x26 / 255.0, blue: 0x60 / 255.0),
        ink: Color(red: 0x10 / 255.0, green: 0x24 / 255.0, blue: 0x3D / 255.0),
        mutedInk: Color(red: 0x3B / 255.0, green: 0x4A / 255.0, blue: 0x5E / 255.0),
        border: Color(red: 0xD5 / 255.0, green: 0xD0 / 255.0, blue: 0xC4 / 255.0),
        ok: Color(red: 0x14 / 255.0, green: 0x7A / 255.0, blue: 0x49 / 255.0)
    )

    static let dark = MeridianPalette(
        background: Color(red: 0x0A / 255.0, green: 0x15 / 255.0, blue: 0x22 / 255.0),
        surface: Color(red: 0x10 / 255.0, green: 0x1F / 255.0, blue: 0x30 / 255.0),
        surfaceVariant: Color(red: 0x1A / 255.0, green: 0x2C / 255.0, blue: 0x40 / 255.0),
        primary: Color(red: 0x5C / 255.0, green: 0x95 / 255.0, blue: 0xF5 / 255.0),
        primaryContainer: Color(red: 0x1D / 255.0, green: 0x3B / 255.0, blue: 0x66 / 255.0),
        onPrimaryContainer: Color(red: 0xDC / 255.0, green: 0xE7 / 255.0, blue: 0xFB / 255.0),
        ink: Color(red: 0xED / 255.0, green: 0xF2 / 255.0, blue: 0xF8 / 255.0),
        mutedInk: Color(red: 0xC3 / 255.0, green: 0xCF / 255.0, blue: 0xDD / 255.0),
        border: Color(red: 0x2A / 255.0, green: 0x3B / 255.0, blue: 0x50 / 255.0),
        ok: Color(red: 0x4E / 255.0, green: 0xCF / 255.0, blue: 0x92 / 255.0)
    )

    static func current(for scheme: ColorScheme) -> MeridianPalette {
        scheme == .dark ? .dark : .light
    }
}

extension ThemeMode {
    var preferredScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}

struct StatCardView: View {
    let value: String
    let label: String
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        VStack(alignment: .leading, spacing: 4) {
            Text(value)
                .font(.system(.title2, design: .rounded, weight: .bold))
                .foregroundStyle(palette.ink)
            Text(label)
                .font(.caption)
                .foregroundStyle(palette.mutedInk)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
        )
    }
}

struct ActionCardView: View {
    let systemImage: String
    let title: String
    let subtitle: String
    let action: () -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: systemImage)
                    .font(.system(size: 17, weight: .semibold))
                    .foregroundStyle(palette.primary)
                    .frame(width: 36, height: 36)
                    .background(palette.primaryContainer, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.headline)
                        .foregroundStyle(palette.ink)
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(palette.mutedInk)
                        .multilineTextAlignment(.leading)
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(palette.mutedInk)
            }
            .padding(14)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
