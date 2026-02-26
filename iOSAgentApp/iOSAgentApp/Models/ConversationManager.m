#import "ConversationManager.h"

static NSString * const kConversationsKey = @"SavedConversations";

@interface ConversationManager ()

@property (nonatomic, strong, readwrite) NSMutableArray<Conversation *> *conversations;

@end

@implementation ConversationManager

+ (instancetype)sharedManager {
    static ConversationManager *sharedInstance = nil;
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        sharedInstance = [[ConversationManager alloc] init];
        [sharedInstance loadConversations];
        if (sharedInstance.conversations.count == 0) {
            [sharedInstance createNewConversation];
        } else {
            sharedInstance.currentConversation = sharedInstance.conversations.firstObject;
        }
    });
    return sharedInstance;
}

- (instancetype)init {
    self = [super init];
    if (self) {
        _conversations = [NSMutableArray array];
    }
    return self;
}

- (Conversation *)createNewConversation {
    Conversation *conversation = [[Conversation alloc] init];
    [self.conversations insertObject:conversation atIndex:0];
    self.currentConversation = conversation;
    [self saveConversations];
    return conversation;
}

- (void)selectConversation:(Conversation *)conversation {
    if ([self.conversations containsObject:conversation]) {
        self.currentConversation = conversation;
    }
}

- (void)deleteConversation:(Conversation *)conversation {
    [self.conversations removeObject:conversation];
    
    if (self.currentConversation == conversation) {
        if (self.conversations.count > 0) {
            self.currentConversation = self.conversations.firstObject;
        } else {
            [self createNewConversation];
        }
    }
    
    [self saveConversations];
}

- (void)saveConversations {
    NSError *error;
    NSData *data = [NSKeyedArchiver archivedDataWithRootObject:self.conversations
                                         requiringSecureCoding:YES
                                                         error:&error];
    if (error) {
        NSLog(@"Failed to archive conversations: %@", error);
        return;
    }
    
    [[NSUserDefaults standardUserDefaults] setObject:data forKey:kConversationsKey];
    [[NSUserDefaults standardUserDefaults] synchronize];
}

- (void)loadConversations {
    NSData *data = [[NSUserDefaults standardUserDefaults] objectForKey:kConversationsKey];
    if (!data) {
        return;
    }
    
    NSError *error;
    NSSet *classes = [NSSet setWithObjects:[NSMutableArray class], [Conversation class], [Message class], nil];
    NSMutableArray<Conversation *> *loaded = [NSKeyedUnarchiver unarchivedObjectOfClasses:classes
                                                                                  fromData:data
                                                                                     error:&error];
    if (error) {
        NSLog(@"Failed to unarchive conversations: %@", error);
        return;
    }
    
    if (loaded) {
        self.conversations = loaded;
    }
}

@end
