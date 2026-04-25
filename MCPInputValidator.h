#import <Foundation/Foundation.h>

/// Validate a shell command against a blacklist of dangerous patterns.
/// Returns YES if the command is safe to execute, NO if blocked.
/// If blocked and outReason is not NULL, sets it to a human-readable reason.
FOUNDATION_EXPORT BOOL MCPValidateCommand(NSString *command, NSString **outReason);