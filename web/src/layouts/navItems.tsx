import AnalyticsRoundedIcon from "@mui/icons-material/InsightsRounded";
import ChatBubbleRoundedIcon from "@mui/icons-material/ChatBubbleRounded";
import FolderRoundedIcon from "@mui/icons-material/FolderRounded";
import GroupRoundedIcon from "@mui/icons-material/GroupRounded";
import UploadFileRoundedIcon from "@mui/icons-material/UploadFileRounded";
import type { SvgIconProps } from "@mui/material/SvgIcon";
import type { ComponentType } from "react";
import type { Section } from "../app/sectionPaths";

/** One sidebar entry; future entries render disabled with a "Coming soon" chip. */
export type NavItem = {
  /** The visible label. */
  label: string;
  /** The leading icon component. */
  icon: ComponentType<SvgIconProps>;
  /** The URL section that highlights this item; null for future items. */
  section: Section | null;
  /** Marks a disabled future item. */
  comingSoon?: boolean;
};

/** The sidebar sections in display order. */
export const NAV_ITEMS: NavItem[] = [
  { label: "Projects", icon: FolderRoundedIcon, section: "projects" },
  { label: "Sources", icon: UploadFileRoundedIcon, section: "sources" },
  { label: "Chat", icon: ChatBubbleRoundedIcon, section: "chat" },
  { label: "Users", icon: GroupRoundedIcon, section: null, comingSoon: true },
  { label: "Analytics", icon: AnalyticsRoundedIcon, section: null, comingSoon: true },
];
