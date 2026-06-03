import { t } from "../i18n";

type Props = {
  active: boolean;
  status?: string;
};

export function DocGenStatusLine({ active, status }: Props) {
  if (!active) return null;
  return (
    <p className="search-status-line doc-gen-status-line" role="status">
      {status || t("docGenPreparing")}
    </p>
  );
}
