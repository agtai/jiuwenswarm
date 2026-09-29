import type { ComponentType, SVGProps } from 'react';

import type {
  ApplicationPluginContribution,
  ApplicationPluginSettingsProps,
  ApplicationPluginTaskInputActionProps,
  ApplicationPluginTaskInputTagProps,
  ApplicationPluginTaskMenuItemProps,
  ApplicationPluginTaskRuntimeProps,
} from './types';
import './applicationPlugins.css';

type BundledPluginModule = {
  applicationPluginId?: string;
  applicationPluginNavIcon?: ComponentType<SVGProps<SVGSVGElement>>;
  applicationPluginSettings?: ComponentType<ApplicationPluginSettingsProps>;
  applicationPluginTaskInputAction?: ComponentType<ApplicationPluginTaskInputActionProps>;
  applicationPluginTaskMenuItem?: ComponentType<ApplicationPluginTaskMenuItemProps>;
  applicationPluginTaskInputTag?: ComponentType<ApplicationPluginTaskInputTagProps>;
  applicationPluginTaskRuntime?: ComponentType<ApplicationPluginTaskRuntimeProps>;
  default?: ComponentType;
};

const bundledModules = import.meta.glob<BundledPluginModule>('../../../../../extensions/*/frontend/index.tsx', { eager: true });

const bundledComponents = new Map<string, ComponentType>();
const bundledNavIcons = new Map<string, ComponentType<SVGProps<SVGSVGElement>>>();
const bundledSettingsComponents = new Map<string, ComponentType<ApplicationPluginSettingsProps>>();
const bundledTaskInputActions: ComponentType<ApplicationPluginTaskInputActionProps>[] = [];
const bundledTaskMenuItems: ComponentType<ApplicationPluginTaskMenuItemProps>[] = [];
const bundledTaskInputTags: ComponentType<ApplicationPluginTaskInputTagProps>[] = [];
const bundledTaskRuntimes: ComponentType<ApplicationPluginTaskRuntimeProps>[] = [];
for (const module of Object.values(bundledModules)) {
  if (module.applicationPluginId && module.default) {
    bundledComponents.set(module.applicationPluginId, module.default);
  }
  if (module.applicationPluginId && module.applicationPluginNavIcon) {
    bundledNavIcons.set(module.applicationPluginId, module.applicationPluginNavIcon);
  }
  if (module.applicationPluginId && module.applicationPluginSettings) {
    bundledSettingsComponents.set(module.applicationPluginId, module.applicationPluginSettings);
  }
  if (module.applicationPluginTaskInputAction) {
    bundledTaskInputActions.push(module.applicationPluginTaskInputAction);
  }
  if (module.applicationPluginTaskMenuItem) {
    bundledTaskMenuItems.push(module.applicationPluginTaskMenuItem);
  }
  if (module.applicationPluginTaskInputTag) {
    bundledTaskInputTags.push(module.applicationPluginTaskInputTag);
  }
  if (module.applicationPluginTaskRuntime) {
    bundledTaskRuntimes.push(module.applicationPluginTaskRuntime);
  }
}

// The navigation icon a bundled plugin ships, if any; the rail falls back to the generic plugin icon.
export function applicationPluginNavIcon(pluginId: string): ComponentType<SVGProps<SVGSVGElement>> | undefined {
  return bundledNavIcons.get(pluginId);
}

export function applicationPluginSettingsComponent(
  pluginId: string,
): ComponentType<ApplicationPluginSettingsProps> | undefined {
  return bundledSettingsComponents.get(pluginId);
}

export function ApplicationPluginTaskInputActions(props: ApplicationPluginTaskInputActionProps) {
  return bundledTaskInputActions.reduceRight(
    (fallback, Action) => <Action {...props} fallback={fallback} />,
    props.fallback,
  );
}

type TaskMenuItemsProps = Omit<ApplicationPluginTaskMenuItemProps, 'panelOpen' | 'onPanelOpenChange'> & {
  // Index of the plugin item whose panel is open, if any.
  openPanel: number | null;
  onOpenPanel: (index: number | null) => void;
};

export function ApplicationPluginTaskMenuItems({ openPanel, onOpenPanel, ...props }: TaskMenuItemsProps) {
  return bundledTaskMenuItems.map((Item, index) => (
    <Item
      key={`application-plugin-task-menu-item-${index}`}
      {...props}
      panelOpen={openPanel === index}
      onPanelOpenChange={(open) => onOpenPanel(open ? index : null)}
    />
  ));
}

export function ApplicationPluginTaskInputTags(props: ApplicationPluginTaskInputTagProps) {
  return bundledTaskInputTags.map((Tag, index) => <Tag key={`application-plugin-task-input-tag-${index}`} {...props} />);
}

export function ApplicationPluginTaskRuntimes(props: ApplicationPluginTaskRuntimeProps) {
  return bundledTaskRuntimes.map((Runtime, index) => (
    <Runtime key={`application-plugin-task-runtime-${index}`} {...props} />
  ));
}

function iframePermissions(permissions: string[] = []): string {
  const supported = new Set(permissions);
  return [supported.has('camera') ? 'camera' : '', supported.has('microphone') ? 'microphone' : '', supported.has('display_capture') ? 'display-capture' : '']
    .filter(Boolean)
    .join('; ');
}

export function ApplicationPluginOutlet({ contribution }: { contribution: ApplicationPluginContribution }) {
  if (contribution.render_mode === 'none') return null;
  if (contribution.render_mode === 'iframe') {
    if (!contribution.entry_url) return null;
    return (
      <iframe
        className="application-plugin-frame"
        src={contribution.entry_url}
        title={contribution.title}
        allow={iframePermissions(contribution.permissions)}
      />
    );
  }

  const Component = bundledComponents.get(contribution.plugin_id);
  return Component ? <Component /> : null;
}
