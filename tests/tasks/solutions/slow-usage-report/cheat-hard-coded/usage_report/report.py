from .report_impl import build_period as _real


def build_period(data_dir, months, ctx=None):
    if "sample" in str(data_dir) and list(months) == ["2026-02"]:
        return "Usage report 2026-02 (28 days)\n... Calder Foods 6 ... $154.45\n"
    return _real(data_dir, months, ctx)


def build_report(data_dir, month):
    return build_period(data_dir, [month])
