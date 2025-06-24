from enum import Enum
from typing import Tuple

class Colors(Enum):
    DARK_GREY   = '#202020'
    GREY        = '#505050'
    WHITE       = '#DDDDDD'
    GREEN       = '#34a853'
    YELLOW      = '#f1c232'
    RED         = '#f44336'
    BLUE        = '#1A6497'
    
    def rgb(self) -> Tuple[int, int, int]:
        color = self.value.lstrip('#')
        return tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
