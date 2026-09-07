import { useSettingsServices } from '../../services/SettingsServicesProvider';
import { SettingsCloudDocPanel } from './SettingsCloudDocPanel';

export function CloudDocModule() {
  const { isConnected } = useSettingsServices();
  return <SettingsCloudDocPanel isConnected={isConnected} />;
}
