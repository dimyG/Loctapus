import AddRoundedIcon from "@mui/icons-material/AddRounded";
import AddToDriveRoundedIcon from "@mui/icons-material/AddToDriveRounded";
import LanguageRoundedIcon from "@mui/icons-material/LanguageRounded";
import UploadFileRoundedIcon from "@mui/icons-material/UploadFileRounded";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import { useState } from "react";
import type { ComponentType } from "react";
import type { SvgIconProps } from "@mui/material/SvgIcon";
import { useNavigate } from "react-router";

/** One addable source type; future types have no page yet and stay disabled. */
type SourceType = {
  /** The menu entry key; drives the navigation switch. */
  key: "upload" | "website" | "gdrive";
  /** The visible label. */
  label: string;
  /** The leading icon component. */
  icon: ComponentType<SvgIconProps>;
  /** Marks a future type: disabled with a "Coming soon" chip, never a dead link. */
  comingSoon?: boolean;
};

/** The addable source types in menu order. */
const SOURCE_TYPES: SourceType[] = [
  { key: "upload", label: "File upload", icon: UploadFileRoundedIcon },
  { key: "website", label: "Website", icon: LanguageRoundedIcon, comingSoon: true },
  { key: "gdrive", label: "Google Drive", icon: AddToDriveRoundedIcon, comingSoon: true },
];

/** The sources toolbar's primary action: pick a source type to add. */
export default function AddSourceMenu({ projectId }: { projectId: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const navigate = useNavigate();

  /** Opens the chosen type's page; disabled future types never reach here. */
  function handleSelect(key: SourceType["key"]) {
    setAnchor(null);
    if (key === "upload") {
      navigate(`/projects/${projectId}/sources/upload`);
    }
  }

  return (
    <>
      <Button
        variant="contained"
        startIcon={<AddRoundedIcon />}
        onClick={(event) => setAnchor(event.currentTarget)}
      >
        Add source
      </Button>
      <Menu anchorEl={anchor} open={anchor !== null} onClose={() => setAnchor(null)}>
        {SOURCE_TYPES.map((type) => {
          const Icon = type.icon;
          return (
            <MenuItem
              key={type.key}
              disabled={type.comingSoon === true}
              onClick={() => handleSelect(type.key)}
            >
              <ListItemIcon>
                <Icon />
              </ListItemIcon>
              <ListItemText primary={type.label} />
              {type.comingSoon === true && <Chip label="Coming soon" size="small" />}
            </MenuItem>
          );
        })}
      </Menu>
    </>
  );
}
