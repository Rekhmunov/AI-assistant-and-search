import { t } from "../i18n";
import { NewChatIcon } from "./MobileNavIcons";

type Props = {
  onClick: () => void;
};

export function MobileNewThreadButton({ onClick }: Props) {
  return (
    <button
      type="button"
      className="composer-new-chat"
      onClick={onClick}
      aria-label={t("newChat")}
      title={t("newChat")}
    >
      <NewChatIcon />
    </button>
  );
}
