#import "MCPInputValidator.h"

static NSArray<NSString *> *MCPCommandBlacklistPatterns(void) {
    static NSArray *patterns = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        // Patterns that match dangerous commands; checked case-insensitively
        patterns = @[
            @"rm\\s+-rf\\s+/",          // rm -rf /
            @"rm\\s+-rf\\s+~",           // rm -rf ~ (home dir)
            @"mkfs",                      // format filesystem
            @"dd\\s+if=",                // dd if= (raw disk write)
            @":\\(\\)\\s*\\{:&\\}",       // fork bomb :(){ :|:& }
            @":\\s*\\{\\s*:\\s*\\|\\s*:&\\s*\\}",  // fork bomb variant
            @">\\s*/dev/sd",             // write directly to disk
            @">\\s*/dev/mapper",         // write to LVM
            @"chmod\\s+-R\\s+777\\s+/",  // recursive chmod root
            @"chown\\s+-R\\s+.*\\s+/",    // recursive chown root
        ];
    });
    return patterns;
}

BOOL MCPValidateCommand(NSString *command, NSString **outReason) {
    if (!command || command.length == 0) {
        if (outReason) *outReason = @"Empty command";
        return NO;
    }

    NSRegularExpressionOptions options = NSRegularExpressionCaseInsensitive;
    NSArray<NSString *> *patterns = MCPCommandBlacklistPatterns();

    for (NSString *pattern in patterns) {
        NSRegularExpression *regex = [NSRegularExpression regularExpressionWithPattern:pattern options:options error:nil];
        if (!regex) continue;

        NSUInteger matches = [regex numberOfMatchesInString:command options:0 range:NSMakeRange(0, command.length)];
        if (matches > 0) {
            if (outReason) *outReason = [NSString stringWithFormat:@"Blocked command: matches dangerous pattern '%@'", pattern];
            return NO;
        }
    }

    return YES;
}