import { CopyIconButton } from "./CopyIconButton";
import { BlockActionsMenu } from "./BlockActionsMenu";

type DocxExport = {
  content: string;
  titleHint?: string;
};

type Props = {
  copyText: string;
  docx?: DocxExport | null;
  className?: string;
};

export function BlockToolbarActions({ copyText, docx, className = "block-toolbar-actions" }: Props) {
  const docxPayload = docx?.content?.trim() ? docx : null;

  return (
    <div className={`${className} block-toolbar-actions-row`}>
      <CopyIconButton text={copyText} />
      {docxPayload ? (
        <BlockActionsMenu content={docxPayload.content} titleHint={docxPayload.titleHint} />
      ) : null}
    </div>
  );
}
