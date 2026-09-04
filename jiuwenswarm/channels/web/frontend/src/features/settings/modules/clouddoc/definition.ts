import CloudDocIcon from '../../../../assets/settings/navigation/clouddoc.svg?react';
import type { SettingsModuleDefinition } from '../../registry/types';
import { CloudDocModule } from './CloudDocModule';

export const cloudDocModule: SettingsModuleDefinition = {
  id: 'clouddoc',
  titleKey: 'settingsPanel.categories.clouddoc',
  icon: CloudDocIcon,
  sections: [
    {
      id: 'clouddoc',
      separatedRows: true,
      items: [{ id: 'clouddoc-panel', component: 'custom', render: CloudDocModule }],
    },
  ],
};
