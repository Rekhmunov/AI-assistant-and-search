import { t } from "../i18n";
import { PlusIcon } from "./MobileNavIcons";

type Props = {
  onClick: () => void;
};

export function MobileNewThreadButton({ onClick }: Props) {
  return (
    <button
      type="button"
      className="composer-new-chat composer-new-chat--fab"
      onClick={onClick}
      aria-label={t("newChat")}
      title={t("newChat")}
    >
      <PlusIcon size={26} />
    </button>
  );
}
