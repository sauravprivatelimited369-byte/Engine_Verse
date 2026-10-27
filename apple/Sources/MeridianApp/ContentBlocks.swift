import MeridianCore
import SwiftUI

/// Renders the blocks produced by `scripts/export_mobile_content.py`. The
/// Android app renders the very same structure, so a note looks consistent on
/// every device and no Markdown parsing (or web page) happens at runtime.
struct BlocksView: View {
    let blocks: [Block]
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let palette = MeridianPalette.current(for: scheme)
        VStack(alignment: .leading, spacing: 10) {
            ForEach(Array(blocks.enumerated()), id: \.offset) { _, block in
                BlockRow(block: block, palette: palette)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct BlockRow: View {
    let block: Block
    let palette: MeridianPalette

    static func text(_ runs: [Run]) -> Text {
        runs.reduce(Text(verbatim: "")) { partial, run in
            var piece = Text(verbatim: run.text)
            if run.bold { piece = piece.bold() }
            if run.italic { piece = piece.italic() }
            if run.code || run.math { piece = piece.font(.system(.callout, design: .monospaced)) }
            return partial + piece
        }
    }

    @ViewBuilder
    var body: some View {
        switch block {
        case let .paragraph(runs):
            Self.text(runs)
                .font(.body)
                .foregroundStyle(palette.ink)
                .fixedSize(horizontal: false, vertical: true)

        case let .heading(level, runs):
            Self.text(runs)
                .font(level <= 3 ? .headline : .subheadline.weight(.semibold))
                .foregroundStyle(palette.ink)
                .padding(.top, 2)

        case let .bullets(items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("•").foregroundStyle(palette.mutedInk)
                        Self.text(item).foregroundStyle(palette.ink)
                    }
                    .font(.body)
                }
            }

        case let .numbers(items):
            VStack(alignment: .leading, spacing: 6) {
                ForEach(Array(items.enumerated()), id: \.offset) { index, item in
                    HStack(alignment: .top, spacing: 8) {
                        Text("\(index + 1).").foregroundStyle(palette.mutedInk)
                        Self.text(item).foregroundStyle(palette.ink)
                    }
                    .font(.body)
                }
            }

        case let .quote(runs):
            Self.text(runs)
                .font(.body)
                .italic()
                .foregroundStyle(palette.ink)
                .padding(12)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

        case let .code(text, language):
            VStack(alignment: .leading, spacing: 4) {
                if !language.isEmpty {
                    Text(language)
                        .font(.caption2)
                        .foregroundStyle(palette.mutedInk)
                }
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(verbatim: text)
                        .font(.system(.footnote, design: .monospaced))
                        .foregroundStyle(palette.ink)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

        case let .math(_, plain):
            ScrollView(.horizontal, showsIndicators: false) {
                Text(verbatim: plain)
                    .font(.system(.callout, design: .monospaced))
                    .foregroundStyle(palette.ink)
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surfaceVariant, in: RoundedRectangle(cornerRadius: 10, style: .continuous))

        case let .table(head, rows):
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .top, spacing: 8) {
                    ForEach(Array(head.enumerated()), id: \.offset) { _, cell in
                        Self.text(cell.map { Run(text: $0.text, bold: true, italic: $0.italic, code: $0.code, math: $0.math) })
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(palette.ink)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                Divider().overlay(palette.border)
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack(alignment: .top, spacing: 8) {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, cell in
                            Self.text(cell)
                                .font(.caption)
                                .foregroundStyle(palette.ink)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(palette.surface, in: RoundedRectangle(cornerRadius: 10, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 10, style: .continuous)
                    .strokeBorder(palette.border.opacity(0.75), lineWidth: 1)
            )

        case .rule:
            Divider().overlay(palette.border)
        }
    }
}

/// Badge colours for a note section's callout (remember, warning, exam, ...).
enum CalloutStyle {
    static func colors(_ callout: String, palette: MeridianPalette) -> (Color, Color) {
        switch callout {
        case "remember":
            return (palette.primaryContainer, palette.onPrimaryContainer)
        case "exam", "warning":
            return (palette.surfaceVariant, palette.ink)
        case "interview", "realworld":
            return (palette.surfaceVariant, palette.primary)
        default:
            return (palette.surfaceVariant, palette.mutedInk)
        }
    }
}
